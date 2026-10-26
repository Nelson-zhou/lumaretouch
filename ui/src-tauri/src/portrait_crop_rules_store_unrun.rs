// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Temporary isolated fixtures; no user catalogue access.
use super::*;
use crate::portrait_crop_rules_core::Rules;
use std::{fs, os::unix::fs::{symlink, DirBuilderExt, PermissionsExt}, sync::atomic::{AtomicU64, Ordering}};
struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        static NEXT: AtomicU64 = AtomicU64::new(0);
        let path = std::env::temp_dir().join(format!("portrait-rule-unrun-{}-{}", std::process::id(), NEXT.fetch_add(1, Ordering::SeqCst)));
        // Refuse pre-existing fixture state; never remove an unowned directory.
        fs::DirBuilder::new().mode(0o700).create(&path).unwrap(); Self(path)
    }
    fn root(&self) -> PathBuf { self.0.join("portrait-crop-rule-catalogue") }
}
impl Drop for Fixture { fn drop(&mut self) { let _ = fs::remove_dir_all(&self.0); } }
fn create(c: &Catalogue) -> Request { Request::Create { catalogue_id: c.catalogue_id.clone(), expected_revision: c.revision, name: "Local intent".into(), rules: Rules { aspect_ratio: 0.75, headroom_fraction: 0.1, head_fraction: 0.6, horizontal_position: 0.5 } } }
#[test]
fn persistence_restart_and_cas_do_not_copy_photo_state() {
    let f = Fixture::new(); let (_, initial) = Store::open(&f.0).unwrap();
    let saved = perform(&f.0, create(&initial)); assert_eq!(saved["status"], "saved");
    let (store, restored) = Store::open(&f.0).unwrap(); assert_eq!(restored.entries.len(), 1); assert_eq!(restored.revision, 1); drop(store);
    let before = fs::read(f.root().join(TARGET)).unwrap();
    let rejected = perform(&f.0, create(&initial)); assert_eq!(rejected["no_change"], true);
    assert_eq!(fs::read(f.root().join(TARGET)).unwrap(), before);
    let text = String::from_utf8(before).unwrap(); for key in ["source_uid", "face_id", "crown", "chin", "rect", "preview_token", "review_confirmed"] { assert!(!text.contains(key)); }
}
#[test]
fn lock_and_prepublication_failure_leave_authoritative_bytes_unchanged() {
    let f = Fixture::new(); let (store, initial) = Store::open(&f.0).unwrap();
    let before = fs::read(f.root().join(TARGET)).unwrap();
    let rejected = perform(&f.0, create(&initial)); assert_eq!(rejected["no_change"], true);
    let partial = open_at(&store.directory, TEMP, libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL).unwrap();
    let error = store.save(&initial.change(&create(&initial)).unwrap()).unwrap_err(); assert!(!error.uncertain);
    assert_eq!(fs::read(f.root().join(TARGET)).unwrap(), before); drop(partial); drop(store);
    // Recovery discards uncommitted scratch only AFTER validating canonical data.
    let (store, restored) = Store::open(&f.0).unwrap(); assert_eq!(restored, initial); assert!(!f.root().join(TEMP).exists()); drop(store);
}
#[test]
fn corrupt_unknown_or_missing_catalogue_never_resets_to_empty() {
    for data in [b"broken".to_vec(), b"{\"schema\":\"future.v2\"}".to_vec()] {
        let f = Fixture::new(); let (store, _) = Store::open(&f.0).unwrap(); drop(store);
        fs::write(f.root().join(TARGET), &data).unwrap();
        assert!(Store::open(&f.0).is_err()); assert_eq!(fs::read(f.root().join(TARGET)).unwrap(), data);
    }
    let f = Fixture::new(); let (store, _) = Store::open(&f.0).unwrap(); drop(store);
    fs::remove_file(f.root().join(TARGET)).unwrap(); assert!(Store::open(&f.0).is_err()); assert!(!f.root().join(TARGET).exists());
}
#[test]
fn no_follow_target_and_scratch_refuse_without_repairing_user_data() {
    let f = Fixture::new(); let (store, initial) = Store::open(&f.0).unwrap(); drop(store);
    let before = fs::read(f.root().join(TARGET)).unwrap();
    symlink(f.root().join(TARGET), f.root().join(TEMP)).unwrap();
    let rejected = perform(&f.0, create(&initial)); assert_eq!(rejected["no_change"], true);
    assert_eq!(fs::read(f.root().join(TARGET)).unwrap(), before);
    fs::remove_file(f.root().join(TEMP)).unwrap();
    fs::rename(f.root().join(TARGET), f.root().join("preserved.json")).unwrap();
    symlink(f.root().join("preserved.json"), f.root().join(TARGET)).unwrap();
    assert!(Store::open(&f.0).is_err()); assert_eq!(fs::read(f.root().join("preserved.json")).unwrap(), before);
}

#[test]
fn stale_fresh_initialization_proof_cannot_overwrite_an_existing_target() {
    let f = Fixture::new(); let (store, initial) = Store::open(&f.0).unwrap();
    let populated = initial.change(&create(&initial)).unwrap(); store.save(&populated).unwrap();
    let before = fs::read(f.root().join(TARGET)).unwrap();
    // Models initialization being called after mkdir/open resolved to an already
    // populated replacement directory: exclusive target creation still refuses.
    let error = store.initialize(&initial).unwrap_err(); assert!(!error.uncertain);
    assert_eq!(fs::read(f.root().join(TARGET)).unwrap(), before);
}
#[test]
fn untrusted_or_symlink_ancestors_are_refused_before_creating_children() {
    let f = Fixture::new(); let real = f.0.join("real");
    fs::DirBuilder::new().mode(0o700).create(&real).unwrap();
    symlink(&real, f.0.join("alias")).unwrap();
    assert!(Store::open(&f.0.join("alias/not-created/app")).is_err());
    assert!(!real.join("not-created").exists());
    let shared = f.0.join("shared"); fs::DirBuilder::new().mode(0o700).create(&shared).unwrap();
    fs::set_permissions(&shared, fs::Permissions::from_mode(0o777)).unwrap();
    assert!(Store::open(&shared.join("not-created/app")).is_err());
    assert!(!shared.join("not-created").exists());
}
