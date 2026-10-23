export function ExportColorSpace({value,onChange}:{value:string;onChange:(value:string)=>void}) {
  return (
                <label>色彩空间 ICC
                  <select value={value} onChange={(e) => onChange(e.target.value)}>
                    <option value="srgb">sRGB（嵌入 ICC）</option>
                    <option value="source">跟随源文件 ICC</option>
                    <option value="adobergb" disabled>AdobeRGB</option>
                    <option value="display_p3" disabled>Display P3</option>
                  </select>
                </label>
  );
}
