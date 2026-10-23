import { invoke } from "@tauri-apps/api/core";
import type { CustomLutPort, LutAsset, LutSnapshot } from "./CustomLutPanel";
const active = new Map<string, Set<string>>();
async function request<T>(payload: Record<string, unknown>, document = ""): Promise<T> {
  const id = crypto.randomUUID();
  const jobs = active.get(document) ?? new Set<string>(); jobs.add(id); active.set(document, jobs);
  try {
    await invoke("custom_lut_request", { request: { ...payload, request_id: id } });
    const end = Date.now() + 120000;
    while (Date.now() < end) {
      const receipt = await invoke<{ pending?: boolean; success?: boolean; error?: string; committed?: boolean; result: T }>("custom_lut_status", { requestId: id });
      if (!receipt.pending) {
        if (!receipt.success) throw new Error((receipt.error ?? "LUT 请求失败") + (receipt.committed ? "；部分提交已发生，请刷新核对" : ""));
        return receipt.result;
      }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    await invoke("custom_lut_cancel", { requestId: id });
    throw new Error("LUT 回执超时，已请求取消；写入结果未确认，请刷新核对，勿重复提交");
  } finally { jobs.delete(id); if (!jobs.size) active.delete(document); }
}
export const customLutPort: CustomLutPort & { state(): Promise<LutSnapshot> } = {
  choose: () => invoke<string | null>("custom_lut_choose"),
  list: () => request<LutAsset[]>({ action: "list" }),
  state: () => request<LutSnapshot>({ action: "state" }),
  import: (path, document, revision) => request<LutAsset>({ action: "import", path, document_id: document, revision }, document),
  recover: (path, document, revision, id) => request<LutAsset>({ action: "recover", path, document_id: document, revision, id }, document),
  select: (document, revision, id, amount) => request<LutSnapshot>({ action: "select", document_id: document, revision, id, amount }, document),
  rename: async (id, name) => { await request({ action: "rename", id, name }); },
  remove: async id => { await request({ action: "remove", id }); },
  restore: async id => { await request({ action: "restore", id }); },
  cancel: document => { for (const id of new Set([...(active.get(document) ?? []), ...(active.get("") ?? [])])) void invoke("custom_lut_cancel", { requestId: id }).catch(() => {}); },
};
