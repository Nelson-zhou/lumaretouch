/** A matching receipt is usable only with a same-document, same-or-newer snapshot.
 * Recipe equality is NOT an acknowledgement (no-op barriers can still fail).
 * Callers apply their current authoritative value, never the historical receipt recipe.
 */
export interface EditReceipt {
  request_id:string; document_id:string; host_doc_rev:number;
}
export function canReconcileEdit(pendingId:string|undefined, receipt:EditReceipt|null|undefined,
  documentId:string, snapshotId:string|undefined, snapshotRevision:number, hasValue:boolean):boolean {
  return !!pendingId && !!documentId && hasValue && snapshotId===documentId && !!receipt &&
    receipt.request_id===pendingId && receipt.document_id===documentId &&
    Number.isSafeInteger(receipt.host_doc_rev) && receipt.host_doc_rev>=0 &&
    Number.isSafeInteger(snapshotRevision) && snapshotRevision>=receipt.host_doc_rev;
}
