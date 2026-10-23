import {useId, useState} from 'react';
import type {LibraryQuery} from './model';
import './controls.css';

export interface LibraryQueryControlsProps {
  query: LibraryQuery;
  onChange: (query: LibraryQuery) => void;
  pending: boolean;
  error: string;
  total: number;
  visible: number;
  selected: number;
  onSelectVisible: () => void;
  onClearSelection: () => void;
}

type Option = {value: string; label: string; colour?: string};
type MultiAxis = 'flags' | 'labels' | 'edited' | 'exported' | 'formats' | 'orientations';

const flagOptions: readonly Option[] = [
  {value: 'accepted', label: '已保留'},
  {value: 'rejected', label: '已拒绝'},
  {value: 'unflagged', label: '未标记'},
];
const labelOptions: readonly Option[] = [
  {value: '红', label: '红', colour: '#e06c6c'},
  {value: '黄', label: '黄', colour: '#e3c176'},
  {value: '绿', label: '绿', colour: '#7bbf8a'},
  {value: '蓝', label: '蓝', colour: '#6f9fd8'},
  {value: '紫', label: '紫', colour: '#b48ad8'},
  {value: '', label: '无标签'},
];
const editedOptions: readonly Option[] = [
  {value: 'yes', label: '已编辑'}, {value: 'no', label: '未编辑'},
];
const exportedOptions: readonly Option[] = [
  {value: 'yes', label: '有成功导出记录'}, {value: 'no', label: '无成功导出记录'},
];
const formatOptions: readonly Option[] = [
  {value: 'jpeg', label: 'JPEG / JPG'},
  {value: 'png', label: 'PNG'},
  {value: 'tiff', label: 'TIFF / TIF'},
  {value: 'webp', label: 'WebP'},
  {value: 'bmp', label: 'BMP'},
  {value: 'dng', label: 'DNG'},
  {value: 'arw', label: 'ARW'},
  {value: 'cr2', label: 'CR2'},
  {value: 'cr3', label: 'CR3'},
  {value: 'nef', label: 'NEF'},
  {value: 'raf', label: 'RAF'},
  {value: 'orf', label: 'ORF'},
  {value: 'rw2', label: 'RW2'},
  {value: 'unknown', label: '未知格式'},
];
const orientationOptions: readonly Option[] = [
  {value: 'landscape', label: '横向'},
  {value: 'portrait', label: '纵向'},
  {value: 'square', label: '正方形'},
  {value: 'unknown', label: '未知方向'},
];
const sortOptions: readonly {value: LibraryQuery['sort']; label: string}[] = [
  {value: 'capture_time', label: '拍摄时间'},
  {value: 'edit_time', label: '编辑时间'},
  {value: 'rating', label: '星级'},
  {value: 'type', label: '文件类型'},
  {value: 'size', label: '文件大小'},
  {value: 'name', label: '文件名'},
  {value: 'import', label: '导入顺序'},
];
const scopeLabels: Record<LibraryQuery['trash'], string> = {
  active: '正常照片', trash: '回收站', all: '全部照片（含回收站）',
};

function MultiChoice({title, values, options, onChange, className = ''}: {
  title: string;
  values: string[];
  options: readonly Option[];
  onChange: (values: string[]) => void;
  className?: string;
}) {
  return <fieldset className={`library-query__group ${className}`}>
    <legend>{title}<span className="library-query__multiple">可多选</span></legend>
    <div className="library-query__choices">
      <button type="button" className="library-query__any" aria-label={`${title}不限`}
        aria-pressed={values.length === 0} onClick={() => onChange([])}>不限</button>
      {options.map(option => <label key={option.value} className="library-query__choice"
        data-selected={values.includes(option.value) ? 'true' : 'false'}>
        <input type="checkbox" checked={values.includes(option.value)}
          onChange={event => onChange(event.target.checked
            ? [...values, option.value]
            : values.filter(value => value !== option.value))}/>
        {option.colour && <span className="library-query__swatch" aria-hidden="true"
          style={{backgroundColor: option.colour}}/>}
        <span>{option.label}</span>
      </label>)}
    </div>
  </fieldset>;
}

function selectionSummary(values: string[], options: readonly Option[]): string {
  return values.map(value => options.find(option => option.value === value)?.label ?? value).join(' / ');
}

export function LibraryQueryControls({query, onChange, pending, error, total, visible, selected,
  onSelectVisible, onClearSelection}: LibraryQueryControlsProps) {
  const id = useId();
  const [mode, setMode] = useState<'quick' | 'professional'>('quick');
  const professional = mode === 'professional';
  const set = <K extends keyof LibraryQuery>(key: K, value: LibraryQuery[K]) => {
    onChange({...query, [key]: value});
  };
  const multi = (axis: MultiAxis, title: string, options: readonly Option[], className = '') => (
    <MultiChoice key={axis} title={title} values={query[axis]} options={options}
      onChange={values => set(axis, values)} className={className}/>
  );
  const hiddenFilters = [
    query.edited.length ? `编辑：${selectionSummary(query.edited, editedOptions)}` : '',
    query.exported.length ? `导出：${selectionSummary(query.exported, exportedOptions)}` : '',
    query.formats.length ? `格式：${selectionSummary(query.formats, formatOptions)}` : '',
    query.orientations.length ? `方向：${selectionSummary(query.orientations, orientationOptions)}` : '',
    query.trash !== 'active' ? `范围：${scopeLabels[query.trash]}` : '',
  ].filter(Boolean);
  const activeGroups = Number(query.rating !== null) + Number(query.flags.length > 0)
    + Number(query.labels.length > 0) + hiddenFilters.length + Number(query.search.length > 0);

  function resetFilters() {
    onChange({...query, rating: null, flags: [], labels: [], edited: [], exported: [],
      formats: [], orientations: [], trash: 'active', search: ''});
  }

  return <section className="library-query" aria-label="照片库筛选与排序" data-mode={mode}>
    <div className="library-query__header">
      <span className="library-query__title">筛选与排序</span>
      <div className="library-query__modes" role="group" aria-label="筛选显示模式">
        <button type="button" aria-pressed={!professional} aria-controls={`${id}-filters`}
          onClick={() => setMode('quick')}>简洁筛选</button>
        <button type="button" aria-pressed={professional} aria-controls={`${id}-filters`}
          onClick={() => setMode('professional')}>专业筛选</button>
      </div>
      <span className="library-query__active-count">{activeGroups > 0 ? `${activeGroups} 组条件生效` : '未添加筛选条件'}</span>
      <button type="button" className="library-query__reset" disabled={activeGroups === 0}
        title="清除全部筛选和文件名搜索，恢复正常照片范围；保留排序方式与升降序"
        onClick={resetFilters}>清除筛选（保留排序）</button>
    </div>

    <div className="library-query__toolbar">
      <label className="library-query__search" htmlFor={`${id}-search`}>
        <span>文件名</span>
        <input id={`${id}-search`} type="search" maxLength={240} value={query.search} placeholder="搜索文件名"
          autoComplete="off" onChange={event => set('search', event.target.value)}/>
      </label>
      <label className="library-query__select" htmlFor={`${id}-sort`}>
        <span>排序</span>
        <select id={`${id}-sort`} value={query.sort}
          onChange={event => set('sort', event.target.value as LibraryQuery['sort'])}>
          {sortOptions.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      </label>
      <label className="library-query__select" htmlFor={`${id}-direction`}>
        <span>顺序</span>
        <select id={`${id}-direction`} value={query.direction}
          onChange={event => set('direction', event.target.value as LibraryQuery['direction'])}>
          <option value="asc">升序</option><option value="desc">降序</option>
        </select>
      </label>
    </div>

    <p id={`${id}-logic`} className="library-query__hint">不同条件同时满足；同一组多选满足任意一项。未选择表示不限。</p>
    {!professional && hiddenFilters.length > 0 && <div className="library-query__hidden" role="status">
      <strong>{hiddenFilters.length} 组隐藏的专业条件仍在生效</strong>
      <span>{hiddenFilters.join('；')}</span>
      <button type="button" onClick={() => setMode('professional')}>展开查看条件</button>
    </div>}

    <div id={`${id}-filters`} className="library-query__filters" aria-describedby={`${id}-logic`}>
      <fieldset className="library-query__group library-query__rating">
        <legend>星级</legend>
        <div className="library-query__rating-inputs">
          <label htmlFor={`${id}-rating-op`}><span className="library-query__sr-only">星级比较条件</span>
            <select id={`${id}-rating-op`} value={query.rating?.op ?? 'all'} onChange={event => {
              const op = event.target.value;
              set('rating', op === 'all' ? null : {op: op as NonNullable<LibraryQuery['rating']>['op'],
                value: query.rating?.value ?? 3});
            }}>
              <option value="all">不限星级</option><option value="gte">至少</option>
              <option value="lte">至多</option><option value="eq">等于</option>
            </select>
          </label>
          <label htmlFor={`${id}-rating-value`}><span className="library-query__sr-only">星级数值</span>
            <select id={`${id}-rating-value`} value={query.rating?.value ?? 3} disabled={!query.rating}
              onChange={event => {
                if (query.rating) set('rating', {...query.rating, value: Number(event.target.value)});
              }}>
              {[0, 1, 2, 3, 4, 5].map(value => <option key={value} value={value}>{value === 0 ? '无星（0 星）' : `${value} 星`}</option>)}
            </select>
          </label>
        </div>
      </fieldset>
      {multi('flags', '旗标', flagOptions)}
      {multi('labels', '颜色标签', labelOptions)}
      {professional && <>
        {multi('edited', '编辑状态', editedOptions)}
        {multi('exported', '导出状态', exportedOptions)}
        {multi('orientations', '照片方向', orientationOptions)}
        {multi('formats', '文件格式', formatOptions, 'library-query__formats')}
        <fieldset className="library-query__group library-query__scope">
          <legend>照片范围</legend>
          <div className="library-query__choices">
            {(['active', 'trash', 'all'] as const).map(value => <label key={value}
              className="library-query__choice" data-selected={query.trash === value ? 'true' : 'false'}>
              <input type="radio" name={`${id}-scope`} value={value} checked={query.trash === value}
                onChange={() => set('trash', value)}/>
              <span>{scopeLabels[value]}</span>
            </label>)}
          </div>
        </fieldset>
      </>}
    </div>

    <div className="library-query__footer">
      <div className="library-query__counts" role="status" aria-live="polite" aria-atomic="true" aria-busy={pending}>
        <span>{pending ? '当前已显示' : '显示'} <strong>{visible}</strong> / {total} 张</span>
        <span>已选 <strong>{selected}</strong> 张</span>
      </div>
      <span className="library-query__scope-caption">范围：{scopeLabels[query.trash]}</span>
      <div className="library-query__selection">
        <button type="button" onClick={onSelectVisible} disabled={pending || !!error || visible === 0}
          title={pending ? '等待筛选更新后再选择' : error ? '筛选结果未确认，暂不可选择' : '选择当前可见的照片'}>选择当前可见</button>
        <button type="button" onClick={onClearSelection} disabled={selected === 0}>清除选择</button>
      </div>
    </div>
    <p className="library-query__hint library-query__selection-hint">批处理仅作用于当前可见的所选照片，隐藏选择保留。</p>
    <p className="library-query__hint">缺失时间始终排末尾；旧工程未记录的编辑时间未知。导出状态依据本项目可用的成功回执。</p>
    {pending && <p className="library-query__pending" role="status">正在更新筛选结果，照片数量可能尚未刷新…</p>}
    {!!error && <p className="library-query__error" role="alert">筛选结果未确认：{error}</p>}
  </section>;
}

export default LibraryQueryControls;
