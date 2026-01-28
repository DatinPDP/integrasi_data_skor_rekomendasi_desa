"use client";

import { useState, useEffect, useRef, useCallback } from 'react';
import { AgGridReact } from 'ag-grid-react';
import {
  ModuleRegistry,
  AllCommunityModule,
  ClientSideRowModelModule,
  ColDef,
  ValueGetterParams
} from 'ag-grid-community';
import * as XLSX from 'xlsx';
import SparkMD5 from 'spark-md5';
import { DashboardRow, StagingData, HistoryChange, VersionMeta } from '../types';

// Register AG Grid Modules
ModuleRegistry.registerModules([AllCommunityModule, ClientSideRowModelModule]);

const API_BASE_URL = "http://localhost:8000";

export const useAdminLogic = () => {
  // ==========================================
  // STATE MANAGEMENT
  // ==========================================

  // --- UI Toggles ---
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [viewModeState, setViewModeState] = useState<'grid' | 'dashboard'>('grid');
  const [isDarkModeEnabled, setIsDarkModeEnabled] = useState(false);

  // Sidebar Section Toggles
  const [isActionsOpen, setIsActionsOpen] = useState(false);
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isLocationOpen, setIsLocationOpen] = useState(true);

  // --- Data & Stats ---
  const [statsTotalRows, setStatsTotalRows] = useState("0");
  const [statsLastUpdateLabel, setStatsLastUpdateLabel] = useState("N/A");
  const [uiStatusMessage, setUiStatusMessage] = useState("");

  // --- Filters ---
  const [targetYear, setTargetYear] = useState("2025");
  const [availableYears] = useState([2025, 2024]);
  const [filterSelProv, setFilterSelProv] = useState("");
  const [filterSelKab, setFilterSelKab] = useState("");
  const [filterSelKec, setFilterSelKec] = useState("");
  const [filterNameSearch, setFilterNameSearch] = useState("");
  const [filterIdListInput, setFilterIdListInput] = useState("");
  const [filterDeleteListInput, setFilterDeleteListInput] = useState("");
  const [isTranslationActive, setIsTranslationActive] = useState(false);
  const [filterSelectedVersion, setFilterSelectedVersion] = useState("");

  // --- Header Search ---
  const [headerSearchTerm, setHeaderSearchTerm] = useState("");
  const [headerSearchOpen, setHeaderSearchOpen] = useState(false);

  // --- Metadata ---
  const [metaVersionsList, setMetaVersionsList] = useState<VersionMeta[]>([]);
  const [metaHierarchyTree, setMetaHierarchyTree] = useState<Record<string, Record<string, string[]>>>({});
  const [metaColumnList, setMetaColumnList] = useState<string[]>([]);

  // --- Staging & History Details ---
  const [stagingDataObject, setStagingDataObject] = useState<StagingData | null>(null);
  const [historyDiffCache, setHistoryDiffCache] = useState<{ [key: string]: HistoryChange[] }>({});
  const [historyOpenDetailsId, setHistoryOpenDetailsId] = useState<string | null>(null);

  // --- Grid & Dashboard Data ---
  const gridRef = useRef<AgGridReact>(null);
  const [rowData, setRowData] = useState<DashboardRow[]>([]);
  const [columnDefs, setColumnDefs] = useState<ColDef[]>([]);
  const [dashboardData, setDashboardData] = useState<DashboardRow[]>([]);
  const [isDashboardCalculated, setIsDashboardCalculated] = useState(false);

  const isFirstRender = useRef(true);

  // ==========================================
  // ==========================================
  // ACTIONS & LOGIC
  // ==========================================

  const ui_ToggleDarkMode = () => setIsDarkModeEnabled(!isDarkModeEnabled);

  // --- Header Search Logic ---
  const action_JumpToColumn = (colName: string) => {
    if (viewModeState !== 'grid') setViewModeState('grid');

    setTimeout(() => {
      if (gridRef.current?.api) {
        gridRef.current.api.ensureColumnVisible(colName);

        setTimeout(() => {
          try {
            gridRef.current?.api.flashCells({ columns: [colName] });
          } catch (e) {
            console.warn("Could not flash cell (might be hidden)", e);
          }
        }, 100);
      }
    }, 100);
  };

  // --- Year Change Logic ---
  const action_YearChanged = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setTargetYear(e.target.value);
    setFilterSelectedVersion("");
    setFilterSelProv("");
    setFilterSelKab("");
    setFilterSelKec("");
    setStagingDataObject(null);
    setStatsTotalRows("0");
    setStatsLastUpdateLabel("N/A");
    setHistoryDiffCache({});
    setHistoryOpenDetailsId(null);
  };

  // --- Fetch Metadata ---
  const fetchVersionHistoryAndHierarchy = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/history/versions/${targetYear}`);
      if (res.ok) {
        const data = await res.json();
        setMetaVersionsList(data.versions || []);
        setMetaHierarchyTree(data.hierarchy || {});
        if (data.versions?.length > 0 && !filterSelectedVersion) {
          setStatsLastUpdateLabel(data.versions[0].ts);
        }
      }
    } catch (e) { console.error("Meta Fetch Error", e); }
  }, [targetYear, filterSelectedVersion]);

  // --- Main Query Logic ---
  const fetchMainGridDataFromAPI = useCallback(async () => {
    if (gridRef.current?.api) gridRef.current.api.showLoadingOverlay();

    if (filterSelectedVersion) setStatsLastUpdateLabel(filterSelectedVersion);
    else if (metaVersionsList.length > 0) setStatsLastUpdateLabel(metaVersionsList[0].ts);
    else setStatsLastUpdateLabel("No Data");

    const params = new URLSearchParams({
      limit: "50000",
      translate: isTranslationActive ? "true" : "false"
    });

    if (filterSelectedVersion) params.append("version", filterSelectedVersion);
    if (filterSelProv) params.append("Provinsi", filterSelProv);
    if (filterSelKab) params.append("Kabupaten/ Kota", filterSelKab);
    if (filterSelKec) params.append("Kecamatan", filterSelKec);
    if (filterNameSearch) params.append("Desa", filterNameSearch);
    if (filterIdListInput.trim()) params.append("ids", filterIdListInput.replace(/\n/g, ","));

    try {
      const res = await fetch(`${API_BASE_URL}/query/${targetYear}?${params}`);
      const data = await res.json();

      if (Array.isArray(data)) {
        setStatsTotalRows(data.length.toLocaleString());
        if (data.length > 0) {
          setMetaColumnList(Object.keys(data[0]));

          const cols = Object.keys(data[0]).map(k => ({
            field: k,
            headerName: k,
            valueGetter: (params: ValueGetterParams) => params.data[k],
            tooltipField: k,
            filter: true,
            sortable: true,
            resizable: true,
            minWidth: 120
          }));

          setColumnDefs(cols);
          setRowData(data);

        } else {
          setStatsTotalRows("0");
          setRowData([]);
          setColumnDefs([]);
        }
      } else if (data.error && data.error === "Table not found.") {
        setStatsTotalRows("0");
        setRowData([]);
      }
    } catch (e) { console.error(e); }
    if (gridRef.current?.api) gridRef.current.api.hideOverlay();
  }, [targetYear, isTranslationActive, filterSelectedVersion, filterSelProv, filterSelKab, filterSelKec, filterNameSearch, filterIdListInput, metaVersionsList]);

  // --- Dashboard Calculation & RowSpan Logic ---
  const calculateDashboardStatsFromAPI = async () => {
    setUiStatusMessage("Calculating...");
    const params = new URLSearchParams();
    params.append("translate", isTranslationActive ? "true" : "false");
    if (filterSelectedVersion) params.append("version", filterSelectedVersion);
    if (filterSelProv) params.append("Provinsi", filterSelProv);
    if (filterSelKab) params.append("Kabupaten/ Kota", filterSelKab);
    if (filterSelKec) params.append("Kecamatan", filterSelKec);
    if (filterNameSearch) params.append("Kode Wilayah Administrasi Desa", filterNameSearch);
    if (filterIdListInput.trim()) params.append("ids", filterIdListInput.replace(/\n/g, ","));

    try {
      const res = await fetch(`${API_BASE_URL}/dashboard/calculate/${targetYear}?${params}`, { method: "POST" });
      const dataRows = await res.json();

      const processedRows = [...dataRows];
      const rowSpans: Record<string, number>[] = new Array(dataRows.length).fill(0).map(() => ({}));
      const mergeKeys = ["NO", "DIMENSI", "SUB DIMENSI", "INDIKATOR"];

      for (const k of mergeKeys) {
        for (let i = 0; i < dataRows.length; i++) {
          if (rowSpans[i][k] === -1) continue;
          let span = 1;
          for (let j = i + 1; j < dataRows.length; j++) {
            let parentsMatch = true;
            const idx = mergeKeys.indexOf(k);
            // Check all parent keys match
            for (let p = 0; p < idx; p++) {
              if (dataRows[i][mergeKeys[p]] !== dataRows[j][mergeKeys[p]]) parentsMatch = false;
            }

            if (dataRows[i][k] === dataRows[j][k] && parentsMatch) {
              span++;
              rowSpans[j][k] = -1;
            } else {
              break;
            }
          }
          rowSpans[i][k] = span;
        }
      }

      processedRows.forEach((row, idx) => { row._rowSpans = rowSpans[idx]; });

      setDashboardData(processedRows);
      setIsDashboardCalculated(true);
      setUiStatusMessage("✅ Done");
    } catch (e) {
      if (viewModeState === 'dashboard') alert("Error: " + (e as Error).message);
      setUiStatusMessage("❌ Error");
    }
  };

  // --- History Details ---
  const ui_ToggleHistoryDetails = async (ts: string) => {
    if (historyOpenDetailsId === ts) {
      setHistoryOpenDetailsId(null);
      return;
    }
    setHistoryOpenDetailsId(ts);
    if (historyDiffCache[ts]) return;

    try {
      const res = await fetch(`${API_BASE_URL}/history/details/${targetYear}?version=${ts}`);
      const data = await res.json();
      setHistoryDiffCache((prev) => ({ ...prev, [ts]: data.changes || [] }));
    } catch (e) { console.error(e); }
  };

  // --- Soft Delete ---
  const action_SoftDeleteIDs = async () => {
    if (!filterDeleteListInput.trim()) return alert("Please enter IDs to delete.");
    if (!confirm("⚠️ Are you sure?")) return;
    setUiStatusMessage("Deleting...");
    const params = new URLSearchParams();
    params.append("ids", filterDeleteListInput);
    params.append("summary", "User deleted from dashboard");

    try {
      const res = await fetch(`${API_BASE_URL}/delete/${targetYear}?${params}`, { method: "POST" });
      const data = await res.json();
      if (data.status === "success") {
        alert(`✅ Deleted ${data.deleted_count} records.\nIDs: ${data.deleted_ids.join(", ")}`);
        setFilterDeleteListInput("");
        fetchVersionHistoryAndHierarchy();
        fetchMainGridDataFromAPI();
        setUiStatusMessage("");
      } else {
        alert("Server Warning: " + (data.message || data.error));
      }
    } catch (err) { alert("❌ Connection Error" + (err as Error).message); }
  };

  // --- Dropdown Helpers ---
  const getKabOptions = () => (filterSelProv && metaHierarchyTree[filterSelProv]) ? Object.keys(metaHierarchyTree[filterSelProv]).sort() : [];
  const getKecOptions = () => (filterSelProv && filterSelKab && metaHierarchyTree[filterSelProv][filterSelKab]) ? metaHierarchyTree[filterSelProv][filterSelKab].sort() : [];

  // --- Upload & Staging ---
  const action_UploadFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Reset UI
    setUiStatusMessage("Preparing...");
    setStagingDataObject(null);

    try {
      // --- ROBUST HASH CACHING ---
      // If user refreshes, we don't want to re-calculate MD5 for 10 seconds.
      // We cache the hash in LocalStorage keyed by the file's unique signature.
      const cacheKey = `upload_hash_${file.name}_${file.size}_${file.lastModified}`;
      let fileHash = localStorage.getItem(cacheKey);

      if (!fileHash) {
        setUiStatusMessage("Hashing file (Integrity Check)...");
        fileHash = await helpers_compute_md5(file);
        try { localStorage.setItem(cacheKey, fileHash); } catch (e) { console.error(e); }
      }

      // Generate the Unique ID for the server
      // If you refresh and pick this file again, this ID stays the same, so server finds the .tmp file.
      const fileUid = `${fileHash}_${file.size}_${file.lastModified}`;

      setUiStatusMessage("Checking server resume status...");

      // Query server: "Do you have this file?"
      const initRes = await fetch(`${API_BASE_URL}/upload/init/${targetYear}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          file_uid: fileUid,
          total_size: file.size,
          total_hash: fileHash
        })
      });
      const initData = await initRes.json();

      if (initData.status === "exists") {
        // File already fully uploaded on server, jump to processing
        setUiStatusMessage("File exists. Processing...");
        await helpers_finalize_upload(initData.upload_id, file.name, fileHash);
        e.target.value = "";
        return;
      }

      // Start Chunking Loop
      let offset = initData.received_bytes || 0;
      const CHUNK_SIZE = 1024 * 1024 * 2; // 2MB Chunks (safe for slow connections)
      const totalSizeMB = (file.size / (1024 * 1024)).toFixed(2);

      while (offset < file.size) {
        const chunkBlob = file.slice(offset, offset + CHUNK_SIZE);

        // UI Progress
        // Example: "Uploading: 12.50 / 50.00 MB (25%)"
        const currentMB = (offset / (1024 * 1024)).toFixed(2);
        const percent = Math.round((offset / file.size) * 100);
        setUiStatusMessage(`Uploading: ${currentMB} / ${totalSizeMB} MB (${percent}%)`);

        // Retry Loop for current chunk
        let retries = 5;
        let chunkSuccess = false;

        while (retries > 0 && !chunkSuccess) {
          try {
            const fd = new FormData();
            fd.append("chunk", chunkBlob);
            fd.append("upload_id", initData.upload_id);
            fd.append("offset", String(offset));
            fd.append("chunk_hash", await helpers_compute_md5(chunkBlob)); // Hash Check per chunk

            const chunkRes = await fetch(`${API_BASE_URL}/upload/chunk/${targetYear}`, {
              method: "POST",
              body: fd
            });

            if (!chunkRes.ok) throw new Error("Server rejected chunk");

            chunkSuccess = true;
            offset += CHUNK_SIZE; // Move to next chunk
          } catch (err) {
            retries--;
            console.warn(`Chunk failed, retrying... (${retries} left)`);
            // Exponential backoff: Wait 1s, then 2s, etc.
            await new Promise(r => setTimeout(r, 1000 * (5 - retries)));
          }
        }

        if (!chunkSuccess) throw new Error("Connection unstable. Upload failed after retries.");
      }

      // Finalize & Process
      setUiStatusMessage("Verifying & Analyzing...");
      await helpers_finalize_upload(initData.upload_id, file.name, fileHash);

      // Success
      e.target.value = "";

    } catch (err) {
      console.error(err);
      setUiStatusMessage("❌ " + ((err as Error).message || "Upload Failed"));
    }
  };

  const helpers_compute_md5 = (blob: Blob): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsArrayBuffer(blob);
      reader.onload = (e) => {
        if (e.target?.result) {
          resolve(SparkMD5.ArrayBuffer.hash(e.target.result as ArrayBuffer));
        } else {
          reject(new Error("Failed to read file for hashing"));
        }
      };
      reader.onerror = reject;
    });
  };

  const helpers_finalize_upload = async (uploadId: string, filename: string, fileHash: string) => {
    const res = await fetch(`${API_BASE_URL}/upload/finalize/${targetYear}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        upload_id: uploadId,
        filename: filename,
        total_hash: fileHash
      })
    });
    const d = await res.json();

    if (d.status === "staged") {
      setStagingDataObject(d);
      setUiStatusMessage("");
    } else {
      throw new Error(d.error || "Processing failed");
    }
  };

  const action_CommitStaged = async () => {
    if (!stagingDataObject) return;
    setUiStatusMessage("Saving...");
    const p = new URLSearchParams({ staging_id: stagingDataObject.staging_id, filename: stagingDataObject.filename });
    try {
      const res = await fetch(`${API_BASE_URL}/commit/${targetYear}?${p}`, { method: "POST" });
      const d = await res.json();
      if (d.status === "success") {
        alert("✅ Saved Successfully!");
        setStagingDataObject(null);
        fetchVersionHistoryAndHierarchy();
        fetchMainGridDataFromAPI();
      } else alert("❌ Fail: " + d.error);
    } catch (err) { alert("❌ Commit Error" + (err as Error).message); }
  };

  // --- Download Excel ---
  const action_DownloadToExcel = () => {
    setUiStatusMessage("Preparing download...");
    try {
      const wb = XLSX.utils.book_new();

      // Sheet 1: Grid
      const gridData: DashboardRow[] = [];
      if (gridRef.current?.api) {
        gridRef.current.api.forEachNodeAfterFilter(node => { if (node.data) gridData.push(node.data); });
      }
      if (gridData.length > 0) {
        const ws_grid = XLSX.utils.json_to_sheet(gridData);
        XLSX.utils.book_append_sheet(wb, ws_grid, "Grid (Filtered)");
      }

      // Sheet 2: Dashboard (If loaded)
      if (dashboardData.length > 0) {
        const ws_dash = XLSX.utils.json_to_sheet(dashboardData);
        XLSX.utils.book_append_sheet(wb, ws_dash, "Dashboard");
      }

      XLSX.writeFile(wb, `export_${targetYear}_${new Date().toISOString().split('T')[0]}.xlsx`);
      setUiStatusMessage("✅ Downloaded");
      setTimeout(() => setUiStatusMessage(""), 2000);
    } catch (error) {
      alert('Download failed: ' + (error as Error).message);
    }
  };

  // ==========================================
  // INITIALIZATION & EFFECTS
  // ==========================================

  // Theme Initialization (Run once on mount)
  useEffect(() => {
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
      setTimeout(() => setIsDarkModeEnabled(true), 0);
    }
  }, []);

  // Fetch Metadata (Run when targetYear changes)
  useEffect(() => {
    const runFetch = async () => {
      await fetchVersionHistoryAndHierarchy();
    };
    runFetch();
  }, [targetYear]);

  // Fetch Data Auto-Apply
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchMainGridDataFromAPI();
    }, 50);
    return () => clearTimeout(timer);
  }, [
    fetchMainGridDataFromAPI, // Dependency added via useCallback
  ]);

  // for instant translation toggle
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    // Wrap in an immediately invoked async function to satisfy linter
    const runFetchMainGridDataFromAPI = async () => {
      await fetchMainGridDataFromAPI();
    };
    runFetchMainGridDataFromAPI();
  }, [isTranslationActive]);

  // Sync Dashboard Calculation
  useEffect(() => {
    if (viewModeState === 'dashboard') {
      const runCalculateDashboardStatsFromAPI = async () => {
        await calculateDashboardStatsFromAPI();
      };
      runCalculateDashboardStatsFromAPI();
    }
  }, [viewModeState, rowData]);

  // Dark Mode Body Class
  useEffect(() => {
    const root = document.documentElement;
    if (isDarkModeEnabled) {
      root.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      root.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  }, [isDarkModeEnabled]);

  return {
    isSidebarOpen, setIsSidebarOpen,
    viewModeState, setViewModeState,
    isDarkModeEnabled, ui_ToggleDarkMode,
    isActionsOpen, setIsActionsOpen,
    isDeleteOpen, setIsDeleteOpen,
    isHistoryOpen, setIsHistoryOpen,
    isLocationOpen, setIsLocationOpen,
    statsTotalRows,
    statsLastUpdateLabel,
    uiStatusMessage, setUiStatusMessage,
    targetYear, setTargetYear, availableYears,
    filterSelProv, setFilterSelProv,
    filterSelKab, setFilterSelKab,
    filterSelKec, setFilterSelKec,
    filterNameSearch, setFilterNameSearch,
    filterIdListInput, setFilterIdListInput,
    filterDeleteListInput, setFilterDeleteListInput,
    isTranslationActive, setIsTranslationActive,
    filterSelectedVersion, setFilterSelectedVersion,
    headerSearchTerm, setHeaderSearchTerm,
    headerSearchOpen, setHeaderSearchOpen,
    metaVersionsList,
    metaHierarchyTree,
    metaColumnList,
    stagingDataObject, setStagingDataObject,
    historyDiffCache,
    historyOpenDetailsId,
    gridRef,
    rowData,
    columnDefs,
    dashboardData,
    isDashboardCalculated,
    action_JumpToColumn,
    action_YearChanged,
    fetchMainGridDataFromAPI,
    calculateDashboardStatsFromAPI,
    ui_ToggleHistoryDetails,
    action_SoftDeleteIDs,
    getKabOptions,
    getKecOptions,
    action_UploadFile,
    action_CommitStaged,
    action_DownloadToExcel
  };
};
