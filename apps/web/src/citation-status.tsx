/** Source binding is separate from PDF loading and semantic support. */
export function CitationStatus({ hasCitations }: { hasCitations: boolean }) {
  return (
    <div>
      <p className="verified-label">
        {hasCitations ? "引用已绑定来源片段" : "未提供可引用答案"}
      </p>
      <details className="source-details">
        <summary>引用说明</summary>
        <p>
          引用绑定不可变文档版本与原文片段；物理引用校验不证明语义支持。PDF
          定位以原文面板实际加载结果为准。
        </p>
      </details>
    </div>
  );
}
