// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED, UNRUN. In-memory owner receipts below are test fixtures only, not
//! application adapters, actual import results or fabricated review evidence.
use crate::{ports::*, schema::*, scheduler::*, DurableRunner};

fn graph(base: &str, preset: Option<ErrorPolicy>) -> Graph {
    let mut nodes = vec![
        Node { id:"source".into(), error_policy:ErrorPolicy::Stop, operation:NodeKind::DirectorySource {
            root:format!("{base}/source"),recursive:true,include_existing:false,extensions:vec!["jpg".into()],settle_ms:250 } },
        Node { id:"import".into(),error_policy:ErrorPolicy::Stop,operation:NodeKind::ManagedImport {
            project_id:"project-one".into(),project_path:format!("{base}/project.lrt"),managed_root:format!("{base}/managed") } },
    ];
    if let Some(policy) = preset {
        nodes.push(Node { id:"preset".into(),error_policy:policy,operation:NodeKind::CompatiblePreset {
            preset_id:"preset-one".into(),preset_sha256:"a".repeat(64),when_all_labels:vec![] } });
    }
    nodes.push(Node { id:"export".into(),error_policy:ErrorPolicy::Stop,operation:NodeKind::Export {
        output_root:format!("{base}/output"),recipe_sha256:"b".repeat(64) } });
    let edges = nodes.windows(2).map(|pair| Edge { from:pair[0].id.clone(),to:pair[1].id.clone() }).collect();
    Graph { schema_version:1,workflow_id:"workflow-one".into(),revision:1,nodes,edges }
}
fn input(base: &str, name: &str) -> InputOccurrence {
    let source_path = format!("{base}/source/{name}");
    let relative_path = name.to_string();
    let source_stat = ["1".into(),"2".into(),"1".into(),"3".into(),"4".into()];
    let source_sha256 = sha256(b"x");
    InputOccurrence { occurrence_id:fingerprint(&(&source_path,&relative_path,&source_stat,&source_sha256)).unwrap(),
        source_path,relative_path,source_sha256,size_bytes:1,source_stamp_sha256:fingerprint(&source_stat).unwrap(),
        source_stat,completion:SourceCompletion::StableRead }
}
fn scheduler(preset: Option<ErrorPolicy>) -> Scheduler {
    let mut run = Scheduler::new(graph("/fixture",preset).validate().unwrap(),"run-one".into()).unwrap();
    run.reduce(&Event::Admit { input:input("/fixture","a.jpg") }).unwrap();
    run
}
fn issue(run: &mut Scheduler) -> Command {
    let command = run.next_command().unwrap().unwrap();
    run.reduce(&Event::Intent { command:command.clone() }).unwrap();
    command
}
fn respond(run: &mut Scheduler, command: &Command, result: ReceiptResult) -> Result<()> {
    run.reduce(&Event::Receipt { receipt:Receipt { schema_version:1,identity:command.identity.clone(),result } })
}
fn preparation(count: u16) -> ImportPreparation {
    ImportPreparation { preparation_id:"fixture-preparation".into(),source_sha256:sha256(b"x"),guard:SavedProjectGuard {
        project_id:"project-one".into(),project_path:"/fixture/project.lrt".into(),project_revision:"disk-one".into(),
        workspace_lease_id:"fixture-lease".into(),saved_clean:true,managed_import_receipt_count:count } }
}
fn imported(run: &mut Scheduler) -> DocumentState {
    let prepare = issue(run);
    respond(run,&prepare,ReceiptResult::ImportPrepared { preparation:preparation(0) }).unwrap();
    let commit = issue(run);
    let document = DocumentState { project_id:"project-one".into(),document_id:"document-one".into(),
        document_revision:"revision-one".into(),source_sha256:sha256(b"x"),receipt_id:"fixture-document-receipt".into() };
    respond(run,&commit,ReceiptResult::Imported { document:document.clone(),import_receipt_id:"fixture-import-receipt".into() }).unwrap();
    document
}
fn assessment() -> PresetAssessment {
    PresetAssessment { report_id:"fixture-report".into(),report_sha256:"c".repeat(64),document_revision:"revision-one".into(),
        preset_sha256:"a".repeat(64),requires_review:true,review:None }
}

#[test]
fn minimal_graph_does_not_invent_a_neutral_preset() {
    let checked = graph("/fixture",None).validate().unwrap();
    assert!(checked.preset().is_none());
    let mut run = scheduler(None); imported(&mut run);
    assert!(matches!(run.next_command().unwrap().unwrap().operation,CommandKind::FreezeExport { .. }));
}
#[test]
fn source_input_export_output_cycles_and_disconnected_graphs_are_refused() {
    let original = graph("/fixture",Some(ErrorPolicy::Stop));
    let mut bad = original.clone(); bad.edges[0].to = "source".into(); assert!(bad.validate().is_err());
    let mut bad = original.clone(); bad.edges[0].from = "export".into(); assert!(bad.validate().is_err());
    let mut bad = original.clone(); bad.edges[1] = Edge { from:"preset".into(),to:"import".into() }; assert!(bad.validate().is_err());
    let mut bad = original; bad.edges.pop(); assert!(bad.validate().is_err());
}
#[test]
fn unsupported_keep_policy_and_future_schema_are_refused() {
    let mut bad = graph("/fixture",None); bad.nodes[1].error_policy = ErrorPolicy::KeepContinue; assert!(bad.validate().is_err());
    let mut bad = graph("/fixture",None); bad.schema_version = 2; assert!(bad.validate().is_err());
    let mut value = serde_json::to_value(graph("/fixture",None)).unwrap(); value["unknown"] = true.into();
    assert!(Graph::from_json(&serde_json::to_vec(&value).unwrap()).is_err());
}
#[test]
fn dirty_project_and_full_receipt_capacity_cannot_be_bypassed() {
    for count in [256,257] {
        let mut run = scheduler(None); let prepare = issue(&mut run);
        assert!(respond(&mut run,&prepare,ReceiptResult::ImportPrepared { preparation:preparation(count) }).is_err());
        assert!(matches!(run.jobs()[0].stage,Stage::PrepareImport));
    }
    let mut run = scheduler(None); let prepare = issue(&mut run);
    let mut value = preparation(0); value.guard.saved_clean = false;
    assert!(respond(&mut run,&prepare,ReceiptResult::ImportPrepared { preparation:value }).is_err());
}
#[test]
fn input_business_occurrence_is_not_content_deduplication() {
    let mut run = scheduler(None);
    let other = input("/fixture","other-copy.jpg");
    assert_eq!(run.jobs()[0].input.source_sha256,other.source_sha256);
    assert_ne!(run.jobs()[0].input.occurrence_id,other.occurrence_id);
    run.reduce(&Event::Admit { input:other.clone() }).unwrap();
    run.reduce(&Event::Admit { input:other }).unwrap();
    assert_eq!(run.jobs().len(),2);
}
#[test]
fn occurrence_digest_rebinding_and_receipt_retargeting_are_rejected() {
    let mut wrong = input("/fixture","a.jpg"); wrong.source_path = "/fixture/source/b.jpg".into();
    assert!(wrong.validate().is_err());
    let mut run = scheduler(None); let command = issue(&mut run);
    let mut identity = command.identity.clone(); identity.workflow_revision += 1;
    let receipt = Receipt { schema_version:1,identity,result:ReceiptResult::ImportPrepared { preparation:preparation(0) } };
    assert!(run.reduce(&Event::Receipt { receipt }).is_err());
    assert_eq!(run.pending(),Some(&command));
}
#[test]
fn unknown_queries_original_intent_and_never_replays_mutation() {
    let mut run = scheduler(None); let prepare = issue(&mut run);
    respond(&mut run,&prepare,ReceiptResult::ImportPrepared { preparation:preparation(0) }).unwrap();
    let commit = issue(&mut run);
    respond(&mut run,&commit,ReceiptResult::Unknown { reason:"transport lost after send".into() }).unwrap();
    assert!(matches!(run.status(),RunStatus::Paused { .. }));
    let query = run.next_command().unwrap().unwrap();
    assert_eq!(query.identity,commit.identity);
    assert!(matches!(query.operation,CommandKind::QueryImport { .. }));
    assert!(!query.operation.is_mutation());
}
#[test]
fn review_requires_actual_owner_receipt_not_a_boolean_ack() {
    let mut run = scheduler(Some(ErrorPolicy::Stop)); imported(&mut run); let command = issue(&mut run);
    respond(&mut run,&command,ReceiptResult::PresetPreflight { assessment:assessment() }).unwrap();
    assert!(matches!(run.status(),RunStatus::Paused { detail:PauseReason::ReviewRequired { .. } }));
    assert!(matches!(run.next_command().unwrap().unwrap().operation,CommandKind::QueryPreset { .. }));
    let mut reviewed = assessment();
    reviewed.review = Some(OwnerReviewReceipt { receipt_id:"fixture-owner-review".into(),report_sha256:reviewed.report_sha256.clone(),
        document_id:"document-one".into(),document_revision:reviewed.document_revision.clone(),preset_sha256:reviewed.preset_sha256.clone() });
    respond(&mut run,&command,ReceiptResult::PresetPreflight { assessment:reviewed }).unwrap();
    assert!(matches!(run.next_command().unwrap().unwrap().operation,CommandKind::ApplyPreset { .. }));
}
#[test]
fn keep_continue_without_retained_readback_pauses() {
    let mut run = scheduler(Some(ErrorPolicy::KeepContinue)); let document = imported(&mut run); let command = issue(&mut run);
    respond(&mut run,&command,ReceiptResult::Failed { code:"fixture_failure".into(),message:"definitive fixture failure".into(),retained_document:None }).unwrap();
    assert!(matches!(run.status(),RunStatus::Paused { .. }));
    respond(&mut run,&command,ReceiptResult::Failed { code:"fixture_failure".into(),message:"definitive fixture failure".into(),retained_document:Some(document) }).unwrap();
    assert!(matches!(run.next_command().unwrap().unwrap().operation,CommandKind::FreezeExport { .. }));
}
#[test]
fn skip_ends_only_the_failed_photo_but_stop_fences_the_run() {
    let mut run = scheduler(Some(ErrorPolicy::Skip));
    run.reduce(&Event::Admit { input:input("/fixture","b.jpg") }).unwrap();
    imported(&mut run); let command = issue(&mut run);
    respond(&mut run,&command,ReceiptResult::Failed { code:"fixture_failure".into(),message:"definitive fixture failure".into(),retained_document:None }).unwrap();
    assert_eq!(run.jobs()[0].stage,Stage::Skipped);
    assert!(matches!(run.next_command().unwrap().unwrap().operation,CommandKind::PrepareImport { .. }));
    run.reduce(&Event::Stop).unwrap();
    assert!(run.next_command().unwrap().is_none());
}
#[test]
fn job_bound_never_evicts_identities() {
    let mut run = Scheduler::new(graph("/fixture",None).validate().unwrap(),"bounded".into()).unwrap();
    for i in 0..MAX_JOBS { run.reduce(&Event::Admit { input:input("/fixture",&format!("{i}.jpg")) }).unwrap(); }
    assert!(run.reduce(&Event::Admit { input:input("/fixture","overflow.jpg") }).is_err());
    assert_eq!(run.jobs().len(),MAX_JOBS);
}

#[test]
fn export_receipt_must_match_every_frozen_target_before_sealed_completion() {
    let mut run = scheduler(None); imported(&mut run); run.reduce(&Event::Seal).unwrap();
    let freeze = issue(&mut run);
    let plan = FrozenExport { plan_id:"fixture-plan".into(),plan_sha256:"d".repeat(64),
        document_revision:"revision-one".into(),output_root:"/fixture/output".into(),recipe_sha256:"b".repeat(64),
        targets:vec!["/fixture/output/a.jpg".into()] };
    respond(&mut run,&freeze,ReceiptResult::ExportFrozen { plan:plan.clone() }).unwrap();
    let start = issue(&mut run);
    assert!(respond(&mut run,&start,ReceiptResult::Exported { plan_id:plan.plan_id.clone(),
        export_receipt_id:"fixture-export".into(),outputs:vec![OutputReceipt {
            path:"/fixture/output/renamed.jpg".into(),sha256:"e".repeat(64),size_bytes:1 }] }).is_err());
    assert_eq!(run.pending(),Some(&start));
    respond(&mut run,&start,ReceiptResult::Exported { plan_id:plan.plan_id,export_receipt_id:"fixture-export".into(),
        outputs:vec![OutputReceipt { path:plan.targets[0].clone(),sha256:"e".repeat(64),size_bytes:1 }] }).unwrap();
    assert_eq!(run.status(),RunStatus::Complete);
}

#[test]
fn required_review_cannot_be_retargeted_to_another_document() {
    let mut run = scheduler(Some(ErrorPolicy::Stop)); imported(&mut run); let command = issue(&mut run);
    let mut report = assessment();
    report.review = Some(OwnerReviewReceipt { receipt_id:"fixture-owner-review".into(),report_sha256:report.report_sha256.clone(),
        document_id:"another-document".into(),document_revision:report.document_revision.clone(),preset_sha256:report.preset_sha256.clone() });
    assert!(respond(&mut run,&command,ReceiptResult::PresetPreflight { assessment:report }).is_err());
    assert_eq!(run.pending(),Some(&command));
}

#[cfg(unix)]
struct Layout(std::path::PathBuf);
#[cfg(unix)]
impl Layout {
    fn new() -> Self {
        let suffix = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root = std::env::temp_dir().join(format!("lrt-workflow-unrun-fixture-{}-{suffix}",std::process::id()));
        std::fs::create_dir(&root).unwrap();
        for directory in ["source","managed","output","journal"] { std::fs::create_dir(root.join(directory)).unwrap(); }
        std::fs::write(root.join("project.lrt"),b"fixture, not a real project").unwrap();
        Self(root)
    }
    fn graph(&self) -> ValidatedGraph { graph(self.0.to_str().unwrap(),None).validate().unwrap() }
}
#[cfg(unix)]
impl Drop for Layout { fn drop(&mut self) { let _ = std::fs::remove_dir_all(&self.0); } }

#[cfg(unix)]
#[test]
fn filesystem_preflight_refuses_overlap_and_symlinks() {
    let layout = Layout::new();
    let mut value = layout.graph().graph().clone();
    if let NodeKind::Export { output_root,.. } = &mut value.nodes[2].operation { *output_root = layout.0.join("source").to_str().unwrap().into(); }
    assert!(value.validate().unwrap().preflight_filesystem().is_err());
    std::os::unix::fs::symlink(layout.0.join("output"),layout.0.join("linked-output")).unwrap();
    let mut value = layout.graph().graph().clone();
    if let NodeKind::Export { output_root,.. } = &mut value.nodes[2].operation { *output_root = layout.0.join("linked-output").to_str().unwrap().into(); }
    assert!(value.validate().unwrap().preflight_filesystem().is_err());
}
#[cfg(unix)]
#[test]
fn durable_restart_returns_query_and_lock_prevents_two_writers() {
    let layout = Layout::new(); let journal = layout.0.join("journal");
    let mut run = DurableRunner::create(&journal,layout.graph(),"restart".into()).unwrap();
    run.admit(input(layout.0.to_str().unwrap(),"a.jpg")).unwrap();
    let first = run.step().unwrap().unwrap();
    assert!(DurableRunner::open(&journal).is_err());
    drop(run);
    let mut reopened = DurableRunner::open(&journal).unwrap();
    let query = reopened.step().unwrap().unwrap();
    assert_eq!(first.identity,query.identity);
    assert!(matches!(query.operation,CommandKind::QueryImport { .. }));
}
#[cfg(unix)]
#[test]
fn durable_source_baseline_preserves_photos_arriving_during_downtime() {
    let layout = Layout::new(); let journal = layout.0.join("journal");
    std::fs::write(layout.0.join("source/old.jpg"),b"old opaque fixture bytes").unwrap();
    let mut run = DurableRunner::create(&journal,layout.graph(),"polling".into()).unwrap();
    let mut source = run.source().unwrap();
    assert_eq!(run.poll_source(&mut source,0).unwrap(),0);
    drop(run);
    std::fs::write(layout.0.join("source/new.jpg"),b"new opaque fixture bytes").unwrap();
    let mut reopened = DurableRunner::open(&journal).unwrap(); let mut source = reopened.source().unwrap();
    assert_eq!(reopened.poll_source(&mut source,0).unwrap(),0);
    assert_eq!(reopened.poll_source(&mut source,300).unwrap(),1);
    assert_eq!(reopened.state().jobs()[0].input.relative_path,"new.jpg");
    assert_eq!(reopened.poll_source(&mut source,600).unwrap(),0);
}

#[cfg(unix)]
#[test]
fn a_corrupt_journal_is_not_recovered_as_success() {
    let layout = Layout::new(); let journal = layout.0.join("journal");
    let run = DurableRunner::create(&journal,layout.graph(),"corruption".into()).unwrap();
    drop(run);
    // Only this test's private journal is changed, never an application record.
    std::fs::write(journal.join("00000000.json"),b"{\"corrupt\":true}").unwrap();
    assert!(DurableRunner::open(&journal).is_err());
}

#[cfg(unix)]
#[test]
fn bounded_poll_preserves_surplus_across_checkpoint_and_restart() {
    let layout = Layout::new(); let journal = layout.0.join("journal");
    let mut definition = layout.graph().graph().clone();
    if let NodeKind::DirectorySource { include_existing,.. } = &mut definition.nodes[0].operation { *include_existing = true; }
    for name in ["a.jpg","b.jpg","c.jpg"] { std::fs::write(layout.0.join("source").join(name),b"opaque fixture").unwrap(); }
    let mut run = DurableRunner::create(&journal,definition.validate().unwrap(),"bounded-poll".into()).unwrap();
    let mut source = run.source().unwrap();
    assert_eq!(run.poll_source_bounded(&mut source,0,1).unwrap(),0);
    assert_eq!(run.poll_source_bounded(&mut source,300,1).unwrap(),1);
    assert_eq!(run.state().jobs().len(),1);
    let checkpoint: serde_json::Value = serde_json::from_str(&source.checkpoint().unwrap()).unwrap();
    let observations = checkpoint["observations"].as_object().unwrap();
    assert_eq!(observations.values().filter(|row| row["acknowledged"] == true).count(),1);
    assert_eq!(observations.values().filter(|row| row["eligible"] == true && row["acknowledged"] == false).count(),2);
    let sequence = run.durable_sequence();
    assert_eq!(run.poll_source_bounded(&mut source,600,1).unwrap(),0);
    assert_eq!(run.durable_sequence(),sequence);
    assert_eq!(run.state().status(),RunStatus::Running);
    drop(run);
    let reopened = DurableRunner::open(&journal).unwrap();
    let mut restored = reopened.source().unwrap();
    assert!(restored.poll(0).unwrap().is_empty());
    let surplus = restored.poll(300).unwrap();
    assert_eq!(surplus.len(),2);
    assert!(surplus.iter().all(|input| input.relative_path != "a.jpg"));
}

#[cfg(unix)]
#[test]
fn bounded_poll_invalid_limit_is_error_atomic_and_duplicates_do_not_consume_slots() {
    let layout = Layout::new(); let journal = layout.0.join("journal");
    let mut definition = layout.graph().graph().clone();
    if let NodeKind::DirectorySource { include_existing,.. } = &mut definition.nodes[0].operation { *include_existing = true; }
    for name in ["a.jpg","b.jpg"] { std::fs::write(layout.0.join("source").join(name),b"opaque fixture").unwrap(); }
    let mut run = DurableRunner::create(&journal,definition.validate().unwrap(),"bounded-duplicate".into()).unwrap();
    let mut source = run.source().unwrap();
    let before = source.checkpoint().unwrap();
    let sequence = run.durable_sequence();
    assert!(run.poll_source_bounded(&mut source,0,0).is_err());
    assert!(run.poll_source_bounded(&mut source,0,MAX_JOBS+1).is_err());
    assert_eq!(source.checkpoint().unwrap(),before);
    assert_eq!(run.durable_sequence(),sequence);
    assert_eq!(run.poll_source_bounded(&mut source,0,1).unwrap(),0);
    let inputs = source.poll(300).unwrap();
    run.admit(inputs[0].clone()).unwrap(); // Simulate persisted admission before acknowledgment.
    assert_eq!(run.poll_source_bounded(&mut source,600,1).unwrap(),0);
    assert_eq!(run.state().jobs().len(),1);
    let checkpoint: serde_json::Value = serde_json::from_str(&source.checkpoint().unwrap()).unwrap();
    let observations = checkpoint["observations"].as_object().unwrap();
    assert_eq!(observations.values().filter(|row| row["acknowledged"] == true).count(),1);
    assert_eq!(observations.values().filter(|row| row["acknowledged"] == false).count(),1);
}

#[cfg(unix)]
#[test]
fn stopped_pending_owner_is_not_effects_settled() {
    let layout = Layout::new(); let journal = layout.0.join("journal");
    let mut run = DurableRunner::create(&journal,layout.graph(),"settlement".into()).unwrap();
    assert_eq!(run.durable_sequence(),0);
    assert!(run.pending_effects_settled());
    run.admit(input(layout.0.to_str().unwrap(),"a.jpg")).unwrap();
    let command = run.step().unwrap().unwrap();
    assert_eq!(run.durable_sequence(),2);
    assert!(!run.pending_effects_settled());
    run.stop().unwrap();
    assert!(!run.pending_effects_settled());
    assert_eq!(run.state().status(),RunStatus::Stopped);
    run.record(Receipt { schema_version:1,identity:command.identity,result:ReceiptResult::Failed {
        code:"fixture_failure".into(),message:"definitive fixture owner failure".into(),retained_document:None } }).unwrap();
    assert!(run.pending_effects_settled()); // Host lease-release confirmation is still separately required.
    assert_eq!(run.durable_sequence(),4);
}

#[cfg(unix)]
#[test]
fn a_pinned_source_descriptor_refuses_a_replacement_tree() {
    let layout = Layout::new();
    let mut source = crate::poll::DirectoryPoller::new(&layout.graph()).unwrap();
    source.poll(0).unwrap();
    let pinned = source.pin_root().unwrap();
    std::fs::rename(layout.0.join("source"),layout.0.join("original-source")).unwrap();
    std::fs::create_dir(layout.0.join("source")).unwrap();
    std::fs::write(layout.0.join("source/replacement.jpg"),b"replacement fixture").unwrap();
    assert!(source.verify_root(&pinned).is_err());
    assert!(source.poll(300).is_err());
    assert!(source.checkpoint().is_err());
}
