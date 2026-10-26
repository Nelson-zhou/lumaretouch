// SPDX-License-Identifier: GPL-3.0-or-later
import {checkedCatalogue, checkedName, checkedReply, rulesFromDraft, type Catalogue, type Mutation, type Transport} from './model.ts';
import type {RuleDraft} from '../model.ts';
export type State = {catalogue: Catalogue | null; busy: boolean; uncertain: Mutation | null; message: string};
const text = (error: unknown) => error instanceof Error ? error.message : '目录操作结果未知。';
/** One app-lifetime owner. Closing/reopening UI never retries a lost mutation. */
export class RulePresetCatalogue {
  private value: State = {catalogue: null, busy: false, uncertain: null, message: ''};
  private listeners = new Set<() => void>();
  constructor(private transport: Transport) {}
  snapshot = () => this.value;
  subscribe = (listener: () => void) => {this.listeners.add(listener); return () => {this.listeners.delete(listener);};};
  private emit(patch: Partial<State>) {this.value = {...this.value, ...patch}; this.listeners.forEach(listener => listener());}
  async refresh(): Promise<void> {
    if (this.value.busy) return;
    this.emit({busy: true});
    try {
      const reply = checkedReply(await this.transport({action: 'list'}));
      if (reply.status !== 'snapshot') throw Error('message' in reply ? reply.message : '目录读取收到错误动作回执。');
      const pending = this.value.uncertain, catalogue = reply.catalogue;
      if (pending && pending.catalogue_id === catalogue.catalogue_id && catalogue.revision <= pending.expected_revision) {
        // A delayed IPC mutation could still start. An unchanged read cannot
        // establish no-write and must not unlock another mutation.
        this.emit({catalogue, message: '已读取目录，但旧保存/删除结果仍未知，版本未前进。仍暂停写入；不会自动重发。'});
      } else {
        this.emit({catalogue, uncertain: null, message: pending ? '已核对最新目录，旧修订已失效，旧请求不能再次覆盖。原操作历史结果未据此认定成功；请检查列表后再操作。' : '已读取本机规则目录；不会应用到照片。'});
      }
    } catch (error) {this.emit({catalogue: null, message: `${text(error)} 列表未确认；未启用保存。`});}
    finally {this.emit({busy: false});}
  }
  private expected() {
    if (this.value.busy || this.value.uncertain) throw Error('请先等待或核对原目录操作；不能重复保存。');
    if (!this.value.catalogue) throw Error('请先刷新并读取有效预设目录。');
    return {catalogue_id: this.value.catalogue.catalogue_id, expected_revision: this.value.catalogue.revision};
  }
  private entry(id: string) {
    this.expected();
    const entry = this.value.catalogue!.entries.find(item => item.id === id);
    if (!entry) throw Error('请选择当前目录中仍存在的预设。');
    return entry;
  }
  create(name: string, draft: RuleDraft) {
    const expected = this.expected(); checkedName(name);
    if (this.value.catalogue!.entries.some(entry => entry.name === name)) throw Error('同名预设已存在；不会覆盖，请另取名称或明确更新。');
    return this.mutate({...expected, action: 'create', name, rules: rulesFromDraft(draft)});
  }
  rename(id: string, name: string) {
    this.entry(id); checkedName(name);
    if (this.value.catalogue!.entries.some(entry => entry.id !== id && entry.name === name)) throw Error('同名预设已存在；未重命名。');
    return this.mutate({...this.expected(), action: 'rename', id, name});
  }
  update(id: string, draft: RuleDraft) {this.entry(id); return this.mutate({...this.expected(), action: 'update', id, rules: rulesFromDraft(draft)});}
  delete(id: string) {this.entry(id); return this.mutate({...this.expected(), action: 'delete', id});}
  private async mutate(request: Mutation): Promise<void> {
    this.emit({busy: true, message: '正在保存规则目录；关闭面板不会取消，不能重复提交。'});
    try {
      const reply = checkedReply(await this.transport(structuredClone(request)));
      if (reply.status === 'rejected') {this.emit({catalogue: null, message: `${reply.message} 本次确认未修改规则目录；请刷新后重新确认。`}); return;}
      if (reply.status === 'uncertain') throw Error(reply.message);
      if (reply.status !== 'saved' && reply.status !== 'no_change') throw Error('目录写入收到错误动作回执。');
      const catalogue = checkedCatalogue(reply.catalogue);
      if (catalogue.catalogue_id !== request.catalogue_id || catalogue.revision !== request.expected_revision + (reply.status === 'saved' ? 1 : 0)) throw Error('目录写入修订回执不一致。');
      const entry = 'id' in request ? catalogue.entries.find(item => item.id === request.id) : catalogue.entries.find(item => item.id === `rule-${catalogue.revision}`);
      if ((request.action === 'delete' && entry) || (request.action !== 'delete' && (!entry ||
          (('name' in request) && entry.name !== request.name) || (('rules' in request) && JSON.stringify(entry.rules) !== JSON.stringify(request.rules))))) throw Error('目录回执未包含明确请求的变更。');
      this.emit({catalogue, uncertain: null, message: reply.status === 'no_change' ? '规则目录内容相同，未新增修改。照片没有改变。' : '已保存本机规则目录。照片没有改变；载入也只改变草稿。'});
    } catch (error) {this.emit({uncertain: structuredClone(request), message: `${text(error)} 结果待核对；请刷新目录，不要重复提交。`});}
    finally {this.emit({busy: false});}
  }
}
