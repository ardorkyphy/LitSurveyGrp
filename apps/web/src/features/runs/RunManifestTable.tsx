type RunManifestTableProps = {
  rows: Record<string, unknown>[];
};

export function RunManifestTable({ rows }: RunManifestTableProps) {
  const visibleRows = rows.slice(0, 50);
  return (
    <div className="panel">
      <div className="section-title">Manifest</div>
      <table>
        <thead>
          <tr><th>Title</th><th>Year</th><th>Journal</th><th>DOI</th><th>PDF</th></tr>
        </thead>
        <tbody>
          {visibleRows.map((row, index) => (
            <tr key={`${row.doi || row.title}-${index}`}>
              <td>{String(row.title || "")}</td>
              <td>{String(row.year || row.publish_date || "")}</td>
              <td>{String(row.journal || "")}</td>
              <td>{String(row.doi || "")}</td>
              <td>{String(row.pdf_status || "")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

