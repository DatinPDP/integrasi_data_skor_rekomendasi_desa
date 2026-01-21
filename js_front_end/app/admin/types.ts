export interface DashboardRow {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
  _rowSpans?: { [key: string]: number };
}

export interface StagingData {
  staging_id: string;
  filename: string;
  diff: {
    added: number;
    changed: number;
    removed: number;
  };
}

export interface HistoryChange {
  type: 'ADD' | 'MOD' | 'DEL';
  id: string;
  desc: string;
}

export interface VersionMeta {
  ts: string;
  label: string;
}
