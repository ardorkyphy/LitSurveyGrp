import type { RunFile } from "./types";

type RunFilesPanelProps = {
  files: RunFile[];
};

export function RunFilesPanel({ files }: RunFilesPanelProps) {
  return (
    <div className="panel">
      <div className="section-title">Files</div>
      <table>
        <thead>
          <tr><th>Name</th><th>Type</th><th>Size</th><th>Path</th></tr>
        </thead>
        <tbody>
          {files.map((file) => (
            <tr key={file.path}>
              <td>{file.name}</td>
              <td>{file.kind}</td>
              <td>{file.size}</td>
              <td className="path-cell">{file.path}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

