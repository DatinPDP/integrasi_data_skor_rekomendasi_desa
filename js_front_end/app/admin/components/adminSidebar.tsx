"use client";

import { useAdminLogic } from '../hooks/useAdminLogic';

type AdminSidebarProps = Pick<ReturnType<typeof useAdminLogic>,
  'isSidebarOpen' | 'setIsSidebarOpen' | 'isDarkModeEnabled' |
  'isActionsOpen' | 'setIsActionsOpen' | 'stagingDataObject' | 'setStagingDataObject' |
  'action_UploadFile' | 'uiStatusMessage' | 'action_CommitStaged' | 'action_DownloadToExcel' |
  'isDeleteOpen' | 'setIsDeleteOpen' | 'filterDeleteListInput' | 'setFilterDeleteListInput' |
  'action_SoftDeleteIDs' | 'isHistoryOpen' | 'setIsHistoryOpen' | 'setFilterSelectedVersion' |
  'fetchMainGridDataFromAPI' | 'filterSelectedVersion' | 'targetYear' | 'action_YearChanged' |
  'availableYears' | 'metaVersionsList' | 'ui_ToggleHistoryDetails' | 'historyOpenDetailsId' |
  'historyDiffCache' | 'isLocationOpen' | 'setIsLocationOpen' | 'filterSelProv' |
  'setFilterSelProv' | 'setFilterSelKab' | 'setFilterSelKec' | 'metaHierarchyTree' |
  'filterSelKab' | 'getKabOptions' | 'filterSelKec' | 'getKecOptions' |
  'filterNameSearch' | 'setFilterNameSearch' | 'filterIdListInput' | 'setFilterIdListInput'
>;

export default function AdminSidebar(props: AdminSidebarProps) {
  const {
    isSidebarOpen, setIsSidebarOpen, isDarkModeEnabled,
    isActionsOpen, setIsActionsOpen, stagingDataObject, setStagingDataObject,
    action_UploadFile, uiStatusMessage, action_CommitStaged, action_DownloadToExcel,
    isDeleteOpen, setIsDeleteOpen, filterDeleteListInput, setFilterDeleteListInput,
    action_SoftDeleteIDs, isHistoryOpen, setIsHistoryOpen, setFilterSelectedVersion,
    fetchMainGridDataFromAPI, filterSelectedVersion, targetYear, action_YearChanged,
    availableYears, metaVersionsList, ui_ToggleHistoryDetails, historyOpenDetailsId,
    historyDiffCache, isLocationOpen, setIsLocationOpen, filterSelProv,
    setFilterSelProv, setFilterSelKab, setFilterSelKec, metaHierarchyTree,
    filterSelKab, getKabOptions, filterSelKec, getKecOptions,
    filterNameSearch, setFilterNameSearch, filterIdListInput, setFilterIdListInput
  } = props;

  return (
    <div className={`sidebar_animation_wrapper relative z-20 shrink-0 transition-all duration-300 ease-in-out 
          ${isSidebarOpen ? 'w-80' : 'w-0'} 
          ${isDarkModeEnabled ? 'bg-slate-800 border-slate-700' : 'bg-white border-slate-200'}`}>

      <button onClick={() => setIsSidebarOpen(!isSidebarOpen)}
        className={`sidebar_toggle_btn absolute -right-3 top-20 w-6 h-6 border rounded-full shadow-md z-50 flex items-center justify-center cursor-pointer transform transition-all duration-300
              ${isSidebarOpen ? 'rotate-0' : 'rotate-180'}
              ${isDarkModeEnabled ? 'bg-slate-800 border-slate-600 text-slate-300 hover:bg-slate-700' : 'bg-white border-slate-200 text-slate-500 hover:bg-slate-50'}`}>
        <span className="text-[14px] font-bold">↔</span>
      </button>

      <div className={`sidebar_content_clipper h-full w-full overflow-hidden flex flex-col border-r 
            ${isDarkModeEnabled ? 'border-slate-700' : 'border-slate-200'}`}>

        <div className="sidebar_inner_content w-80 h-full overflow-y-auto custom-scrollbar flex flex-col p-4">

          {/* 1. SIDEBAR ACTIONS / UPLOAD */}
          <div className={`sidebar_section_upload mb-5 border-b pb-4 ${isDarkModeEnabled ? 'border-slate-700' : 'border-gray-100'}`}>
            <div onClick={() => setIsActionsOpen(!isActionsOpen)} className="flex justify-between items-center cursor-pointer mb-3 group select-none">
              <h3 className={`sidebar_section_title text-xs font-bold uppercase tracking-wider transition-colors 
                      ${isDarkModeEnabled ? 'text-gray-400 group-hover:text-gray-300' : 'text-gray-400 group-hover:text-gray-600'}`}>🚀 Actions</h3>
              <span className={`text-[14px] font-bold transition-transform duration-200 ${isActionsOpen ? 'rotate-90' : 'rotate-0'} ${isDarkModeEnabled ? 'text-gray-400' : 'text-gray-400'}`}>›</span>
            </div>

            {isActionsOpen && (
              <div className="sidebar_upload_group space-y-3">
                <div className="sidebar_upload_label_group flex items-center gap-2 mb-1">
                  <span className={`text-[12px] font-bold uppercase tracking-wider ${isDarkModeEnabled ? 'text-slate-400' : 'text-slate-500'}`}>Database Import</span>
                  <div className={`h-px flex-1 ${isDarkModeEnabled ? 'bg-slate-700' : 'bg-slate-200'}`}></div>
                </div>

                {!stagingDataObject ? (
                  <div className="sidebar_upload_dropzone_container">
                    <label className={`sidebar_upload_dropzone flex flex-col items-center justify-center w-full h-12 border-2 border-dashed rounded-lg cursor-pointer transition-all group
                         ${isDarkModeEnabled ? 'bg-slate-800 border-slate-600 hover:border-blue-500 hover:bg-slate-700' : 'bg-blue-50/50 border-blue-300 hover:bg-blue-100 hover:border-blue-400'}`}>
                      <div className="flex flex-col items-center justify-center pt-2 pb-3">
                        <div className={`mb-1 transition-transform group-hover:scale-110 
                              ${isDarkModeEnabled ? 'text-slate-400 group-hover:text-blue-400' : 'text-blue-400 group-hover:text-blue-600'}`}>
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path></svg>
                        </div>
                        <p className={`text-[10px] font-bold ${isDarkModeEnabled ? 'text-slate-300' : 'text-slate-600 group-hover:text-blue-700'}`}>Upload Data</p>
                      </div>
                      <input type="file" onChange={action_UploadFile} className="sidebar_input_file hidden" accept=".xlsb, .xlsx" />
                    </label>
                    <div className="sidebar_status_msg_container min-h-[16px] mt-1 text-center">
                      {uiStatusMessage && <p className="sidebar_status_msg text-[12px] text-blue-600 font-bold animate-pulse">{uiStatusMessage}</p>}
                    </div>
                  </div>
                ) : (
                  <div className={`sidebar_staging_review_panel border rounded-lg shadow-sm overflow-hidden 
                       ${isDarkModeEnabled ? 'bg-slate-800 border-slate-600' : 'bg-white border-slate-200'}`}>
                    <div className={`sidebar_staging_header px-3 py-2 border-b flex items-center justify-between
                          ${isDarkModeEnabled ? 'bg-amber-900/20 border-amber-800/50' : 'bg-amber-50 border-amber-100'}`}>
                      <span className={`text-[12px] font-bold ${isDarkModeEnabled ? 'text-amber-500' : 'text-amber-700'}`}>⚠️ Review Changes</span>
                      <div className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></div>
                    </div>
                    <div className="p-3">
                      <p className={`sidebar_staging_filename text-[12px] mb-3 truncate font-mono p-1 rounded 
                            ${isDarkModeEnabled ? 'bg-slate-900 text-slate-400' : 'bg-slate-100 text-slate-500'}`}>{stagingDataObject.filename}</p>
                      <div className="sidebar_staging_stats_grid grid grid-cols-3 gap-2 mb-3 text-center">
                        <div className={`stat_box_new flex flex-col border rounded p-1 
                               ${isDarkModeEnabled ? 'bg-green-900/20 border-green-800' : 'bg-green-50 border-green-200'}`}>
                          <span className={`text-[9px] font-bold ${isDarkModeEnabled ? 'text-green-400' : 'text-green-700'}`}>NEW</span>
                          <span className={`text-xs font-mono font-bold ${isDarkModeEnabled ? 'text-slate-200' : 'text-slate-700'}`}>{stagingDataObject.diff.added}</span>
                        </div>
                        <div className={`stat_box_mod flex flex-col border rounded p-1 
                               ${isDarkModeEnabled ? 'bg-blue-900/20 border-blue-800' : 'bg-blue-50 border-blue-200'}`}>
                          <span className={`text-[9px] font-bold ${isDarkModeEnabled ? 'text-blue-400' : 'text-blue-700'}`}>MOD</span>
                          <span className={`text-xs font-mono font-bold ${isDarkModeEnabled ? 'text-slate-200' : 'text-slate-700'}`}>{stagingDataObject.diff.changed}</span>
                        </div>
                        <div className={`stat_box_del flex flex-col border rounded p-1 
                               ${isDarkModeEnabled ? 'bg-red-900/20 border-red-800' : 'bg-red-50 border-red-200'}`}>
                          <span className={`text-[9px] font-bold ${isDarkModeEnabled ? 'text-red-400' : 'text-red-700'}`}>DEL</span>
                          <span className={`text-xs font-mono font-bold ${isDarkModeEnabled ? 'text-slate-200' : 'text-slate-700'}`}>{stagingDataObject.diff.removed}</span>
                        </div>
                      </div>
                      <div className="sidebar_staging_actions flex gap-2">
                        <button onClick={action_CommitStaged} className={`sidebar_btn_commit flex-1 text-white py-1.5 rounded text-[12px] font-bold shadow-sm transition 
                              ${isDarkModeEnabled ? 'bg-blue-600 hover:bg-blue-500' : 'bg-slate-800 hover:bg-slate-900'}`}>Commit to DB</button>
                        <button onClick={() => setStagingDataObject(null)} className={`sidebar_btn_cancel px-3 border rounded text-[12px] font-bold transition 
                              ${isDarkModeEnabled ? 'border-slate-600 text-slate-300 hover:bg-slate-700' : 'border-slate-300 text-slate-600 hover:bg-slate-50'}`}>Cancel</button>
                      </div>
                    </div>
                  </div>
                )}

                <button onClick={action_DownloadToExcel} className={`sidebar_btn_download_excel w-full border py-2 rounded text-xs font-bold transition flex justify-center items-center gap-2 
                     ${isDarkModeEnabled ? 'bg-green-900/20 text-green-400 border-green-800 hover:bg-green-900/40' : 'bg-green-50 text-green-700 border-green-600 hover:bg-green-100'}`}>
                  <span>📥</span> Download Excel
                </button>
              </div>
            )}
          </div>

          {/* 2. SIDEBAR DELETE */}
          <div className={`sidebar_section_delete mb-5 border-b pb-4 ${isDarkModeEnabled ? 'border-slate-700' : 'border-gray-100'}`}>
            <div onClick={() => setIsDeleteOpen(!isDeleteOpen)} className="flex justify-between items-center cursor-pointer mb-2 group select-none">
              <h3 className="sidebar_section_title text-xs font-bold text-red-400 uppercase tracking-wider group-hover:text-red-500 transition-colors">🗑️ Soft Delete</h3>
              <span className={`text-[14px] font-bold transition-transform duration-200 ${isDeleteOpen ? 'rotate-90' : 'rotate-0'} ${isDarkModeEnabled ? 'text-gray-400' : 'text-gray-400'}`}>›</span>
            </div>

            {isDeleteOpen && (
              <div>
                <div className="mb-2">
                  <textarea value={filterDeleteListInput} onChange={e => setFilterDeleteListInput(e.target.value)}
                    className={`sidebar_input_delete_ids w-full border p-2 rounded text-xs h-16 font-mono focus:border-red-500 focus:ring-1 focus:ring-red-200 outline-none 
                       ${isDarkModeEnabled ? 'bg-slate-900 border-red-900/50 text-red-100 placeholder-red-100/50' : 'border-red-200 text-gray-700'}`}
                    placeholder="Paste IDs here to drop from Live view..."></textarea>
                </div>
                <button onClick={action_SoftDeleteIDs} className={`sidebar_btn_confirm_delete w-full border py-1.5 rounded text-xs font-bold transition 
                     ${isDarkModeEnabled ? 'bg-red-900/20 text-red-400 border-red-800 hover:bg-red-900/40' : 'bg-red-50 text-red-600 border-red-200 hover:bg-red-100 hover:text-red-700'}`}>
                  Confirm Delete
                </button>
              </div>
            )}
          </div>

          {/* 3. SIDEBAR HISTORY */}
          <div className={`sidebar_section_history mb-5 border-b pb-4 ${isDarkModeEnabled ? 'border-slate-700' : 'border-gray-100'}`}>
            <div onClick={() => setIsHistoryOpen(!isHistoryOpen)} className="flex justify-between items-center cursor-pointer mb-2 group select-none">
              <h3 className={`sidebar_section_title text-xs font-bold uppercase tracking-wider transition-colors 
                      ${isDarkModeEnabled ? 'text-gray-400 group-hover:text-gray-300' : 'text-gray-400 group-hover:text-gray-600'}`}>⏳ History & Changes</h3>
              <span className={`text-[14px] font-bold transition-transform duration-200 ${isHistoryOpen ? 'rotate-90' : 'rotate-0'} ${isDarkModeEnabled ? 'text-gray-400' : 'text-gray-400'}`}>›</span>
            </div>

            {isHistoryOpen && (
              <div>
                <div onClick={() => { setFilterSelectedVersion(""); fetchMainGridDataFromAPI(); }}
                  className={`cursor-pointer mb-2 p-2 rounded border transition-colors flex justify-between items-center 
                       ${!filterSelectedVersion
                      ? (isDarkModeEnabled ? 'bg-green-900/20 border-green-800' : 'bg-green-50 border-green-200')
                      : (isDarkModeEnabled ? 'bg-slate-800 border-slate-600 hover:bg-slate-700' : 'bg-white border-gray-200 hover:bg-gray-50')}`}>
                  <span className={`text-xs font-bold ${!filterSelectedVersion
                    ? (isDarkModeEnabled ? 'text-green-400' : 'text-green-700')
                    : (isDarkModeEnabled ? 'text-gray-300' : 'text-gray-600')}`}>🟢 Live (Current)</span>
                  {!filterSelectedVersion && <span className="text-[10px] text-green-600 font-bold">ACTIVE</span>}
                </div>

                <select value={targetYear} onChange={action_YearChanged} className={`sidebar_select_year w-full border mb-2 p-2 rounded text-xs focus:ring-1 focus:ring-blue-500 outline-none font-bold 
                     ${isDarkModeEnabled ? 'bg-slate-900 border-slate-600 text-blue-400' : 'bg-blue-50 border-blue-300 text-blue-900'}`}>
                  {availableYears.map(y => <option key={y} value={y}>{y}</option>)}
                </select>

                <div className="space-y-2 max-h-[700px] overflow-y-auto custom-scrollbar pr-1">
                  {metaVersionsList.map(v => (
                    <div key={v.ts} className={`border rounded overflow-hidden flex flex-col 
                         ${isDarkModeEnabled ? 'bg-slate-800 border-slate-700' : 'bg-white'}`}>
                      <div className={`p-2 flex flex-col gap-1 border-b 
                           ${isDarkModeEnabled ? 'border-slate-700 bg-slate-800' : 'border-gray-50 bg-gray-50/50'}`}>
                        <div className="flex justify-between items-start">
                          <span className={`text-[10px] font-mono ${isDarkModeEnabled ? 'text-gray-400' : 'text-gray-500'}`}>{v.ts}</span>
                          <span className={`text-[9px] px-1 rounded ${isDarkModeEnabled ? 'bg-slate-700 text-gray-300' : 'bg-gray-200 text-gray-600'}`}>{v.label.split(' - ')[1] || 'Commit'}</span>
                        </div>
                        <div className="flex gap-2 mt-1">
                          <button onClick={() => { setFilterSelectedVersion(v.ts); fetchMainGridDataFromAPI(); }}
                            className={`flex-1 py-1 text-[10px] font-bold rounded border transition-colors 
                                  ${filterSelectedVersion === v.ts
                                ? 'bg-blue-600 text-white border-blue-600'
                                : (isDarkModeEnabled ? 'bg-slate-700 text-gray-300 border-slate-600 hover:bg-slate-600' : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50')}`}>View Data</button>
                          <button onClick={() => ui_ToggleHistoryDetails(v.ts)} className={`px-2 py-1 text-[10px] font-bold rounded border 
                                ${isDarkModeEnabled ? 'border-slate-600 text-slate-400 hover:bg-slate-700' : 'border-gray-300 text-gray-500 hover:bg-gray-100'}`}>{historyOpenDetailsId === v.ts ? 'Hide' : 'Details'}</button>
                        </div>
                      </div>
                      {historyOpenDetailsId === v.ts && (
                        <div className={`border-t p-2 ${isDarkModeEnabled ? 'bg-slate-900 border-slate-700' : 'bg-slate-50 border-gray-200'}`}>
                          {!historyDiffCache[v.ts] ? (
                            <div className="text-center py-2 text-gray-400 text-[10px] animate-pulse">Loading diff...</div>
                          ) : (
                            <div>
                              <div className="grid grid-cols-3 gap-2 text-center mb-2">
                                <div className={`flex flex-col border rounded p-1 ${isDarkModeEnabled ? 'bg-green-900/20 border-green-800' : 'bg-green-50 border-green-200'}`}>
                                  <span className={`text-[9px] font-bold ${isDarkModeEnabled ? 'text-green-400' : 'text-green-700'}`}>ADD</span>
                                  <span className={`text-xs font-mono font-bold ${isDarkModeEnabled ? 'text-slate-200' : 'text-slate-700'}`}>{(historyDiffCache[v.ts] || []).filter(x => x.type === 'ADD').length}</span>
                                </div>
                                <div className={`flex flex-col border rounded p-1 ${isDarkModeEnabled ? 'bg-blue-900/20 border-blue-800' : 'bg-blue-50 border-blue-200'}`}>
                                  <span className={`text-[9px] font-bold ${isDarkModeEnabled ? 'text-blue-400' : 'text-blue-700'}`}>MOD</span>
                                  <span className={`text-xs font-mono font-bold ${isDarkModeEnabled ? 'text-slate-200' : 'text-slate-700'}`}>{(historyDiffCache[v.ts] || []).filter(x => x.type === 'MOD').length}</span>
                                </div>
                                <div className={`flex flex-col border rounded p-1 ${isDarkModeEnabled ? 'bg-red-900/20 border-red-800' : 'bg-red-50 border-red-200'}`}>
                                  <span className={`text-[9px] font-bold ${isDarkModeEnabled ? 'text-red-400' : 'text-red-700'}`}>DEL</span>
                                  <span className={`text-xs font-mono font-bold ${isDarkModeEnabled ? 'text-slate-200' : 'text-slate-700'}`}>{(historyDiffCache[v.ts] || []).filter(x => x.type === 'DEL').length}</span>
                                </div>
                              </div>
                              <ul className="space-y-2 text-[10px] font-mono">
                                {(historyDiffCache[v.ts] || []).map((change, i) => (
                                  <li key={i} className={`border-b pb-1 last:border-0 ${isDarkModeEnabled ? 'border-slate-700' : 'border-gray-100'}`}>
                                    <div className="flex items-center gap-1 mb-0.5">
                                      {change.type === 'ADD' && <span className="text-green-600 font-bold">[+] ADD</span>}
                                      {change.type === 'DEL' && <span className="text-red-600 font-bold">[-] DEL</span>}
                                      {change.type === 'MOD' && <span className="text-blue-600 font-bold">[~] MOD</span>}
                                      <span className={`font-bold ${isDarkModeEnabled ? 'text-slate-300' : 'text-slate-700'}`}>{change.id}</span>
                                    </div>
                                    <div className={`whitespace-pre-wrap pl-8 leading-tight ${isDarkModeEnabled ? 'text-gray-400' : 'text-gray-500'}`}>{change.desc}</div>
                                  </li>
                                ))}
                                {historyDiffCache[v.ts].length === 0 && <li className="text-gray-400 italic text-center">No structural changes found.</li>}
                              </ul>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* 4. SIDEBAR LOCATION */}
          <div className={`sidebar_section_location mb-5 border-b pb-4 ${isDarkModeEnabled ? 'border-slate-700' : 'border-gray-100'}`}>
            <div onClick={() => setIsLocationOpen(!isLocationOpen)} className="flex justify-between items-center cursor-pointer mb-3 group select-none">
              <h3 className={`sidebar_section_title text-xs font-bold uppercase tracking-wider transition-colors 
                      ${isDarkModeEnabled ? 'text-gray-400 group-hover:text-gray-300' : 'text-gray-400 group-hover:text-gray-600'}`}>📍 Location</h3>
              <span className={`text-[14px] font-bold transition-transform duration-200 ${isLocationOpen ? 'rotate-90' : 'rotate-0'} ${isDarkModeEnabled ? 'text-gray-400' : 'text-gray-400'}`}>›</span>
            </div>

            {isLocationOpen && (
              <div className="space-y-3">
                <div className="sidebar_location_filter_prov_group">
                  <label className={`block text-[12px] font-bold mb-1 ${isDarkModeEnabled ? 'text-gray-400' : 'text-gray-500'}`}>PROVINSI</label>
                  <select value={filterSelProv} onChange={e => { setFilterSelProv(e.target.value); setFilterSelKab(""); setFilterSelKec(""); }}
                    className={`sidebar_select_prov w-full border p-1.5 rounded text-xs focus:border-blue-500 outline-none 
                          ${isDarkModeEnabled ? 'bg-slate-900 border-slate-600 text-slate-300' : 'bg-white text-black'}`}>
                    <option value="">- All -</option>
                    {Object.keys(metaHierarchyTree).sort().map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
                <div className="sidebar_location_filter_kab_group">
                  <label className={`block text-[12px] font-bold mb-1 ${isDarkModeEnabled ? 'text-gray-400' : 'text-gray-500'}`}>KABUPATEN/KOTA</label>
                  <select value={filterSelKab} onChange={e => { setFilterSelKab(e.target.value); setFilterSelKec(""); }} disabled={!filterSelProv}
                    className={`sidebar_select_kab w-full border p-1.5 rounded text-xs focus:border-blue-500 outline-none 
                          ${isDarkModeEnabled ? 'bg-slate-900 border-slate-600 text-slate-300' : 'bg-white text-black'} 
                          ${!filterSelProv ? (isDarkModeEnabled ? 'bg-slate-800' : 'bg-gray-100') : ''}`}>
                    <option value="">- All -</option>
                    {getKabOptions().map(k => <option key={k} value={k}>{k}</option>)}
                  </select>
                </div>
                <div className="sidebar_location_filter_kec_group">
                  <label className={`block text-[12px] font-bold mb-1 ${isDarkModeEnabled ? 'text-gray-400' : 'text-gray-500'}`}>KECAMATAN</label>
                  <select value={filterSelKec} onChange={e => setFilterSelKec(e.target.value)} disabled={!filterSelKab}
                    className={`sidebar_select_kec w-full border p-1.5 rounded text-xs focus:border-blue-500 outline-none 
                           ${isDarkModeEnabled ? 'bg-slate-900 border-slate-600 text-slate-300' : 'bg-white text-black'}
                           ${!filterSelKab ? (isDarkModeEnabled ? 'bg-slate-800' : 'bg-gray-100') : ''}`}>
                    <option value="">- All -</option>
                    {getKecOptions().map((c: string) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div className="sidebar_location_filter_search_group mb-3">
                  <input type="text" value={filterNameSearch} onChange={e => setFilterNameSearch(e.target.value)}
                    className={`sidebar_input_search_name w-full border p-2 rounded text-xs focus:border-blue-500 outline-none 
                           ${isDarkModeEnabled ? 'bg-slate-900 border-slate-600 text-slate-300' : 'text-black'}`} placeholder="Search Desa Name..." />
                </div>
                <div className="sidebar_search_ids mb-3">
                  <textarea value={filterIdListInput} onChange={e => setFilterIdListInput(e.target.value)}
                    className={`sidebar_input_search_ids w-full mb-2 border p-2 rounded text-xs h-20 font-mono focus:border-blue-500 outline-none 
                          ${isDarkModeEnabled ? 'bg-slate-900 border-slate-600 text-slate-300' : 'text-black'}`}
                    placeholder="Paste IDs here (comma or newline separated) to search by ID Desa..."></textarea>
                </div>
                <button onClick={fetchMainGridDataFromAPI} className={`sidebar_btn_apply_filter w-full text-white py-2 rounded text-xs font-bold transition shadow-sm 
                      ${isDarkModeEnabled ? 'bg-slate-600 hover:bg-slate-500' : 'bg-slate-700 hover:bg-slate-800'}`}>Apply Filters</button>
              </div>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}
