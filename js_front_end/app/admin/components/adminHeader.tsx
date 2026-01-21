"use client";

import { useAdminLogic } from '../hooks/useAdminLogic';

type AdminHeaderProps = Pick<ReturnType<typeof useAdminLogic>,
  'isDarkModeEnabled' |
  'statsTotalRows' |
  'statsLastUpdateLabel' |
  'headerSearchTerm' |
  'setHeaderSearchTerm' |
  'setHeaderSearchOpen' |
  'headerSearchOpen' |
  'metaColumnList' |
  'action_JumpToColumn' |
  'viewModeState' |
  'setViewModeState' |
  'isTranslationActive' |
  'setIsTranslationActive' |
  'calculateDashboardStatsFromAPI' |
  'ui_ToggleDarkMode'
>;

export default function AdminHeader(props: AdminHeaderProps) {
  const {
    isDarkModeEnabled,
    statsTotalRows,
    statsLastUpdateLabel,
    headerSearchTerm,
    setHeaderSearchTerm,
    setHeaderSearchOpen,
    headerSearchOpen,
    metaColumnList,
    action_JumpToColumn,
    viewModeState,
    setViewModeState,
    isTranslationActive,
    setIsTranslationActive,
    calculateDashboardStatsFromAPI,
    ui_ToggleDarkMode
  } = props;

  return (
    <div className={`header_main_container p-3 flex justify-between items-center shadow-md z-20 shrink-0 border-b 
        ${isDarkModeEnabled ? 'bg-slate-800 text-white border-slate-700' : 'bg-slate-800 text-white border-slate-700'}`}>

      <div className="header_left_group flex items-center gap-6">
        <h1 className="header_title_label text-lg font-bold flex items-center gap-2">
          Admin | data skor rekomendasi desa
        </h1>

        <div className="header_stats_bar bg-slate-900/50 px-3 py-1 rounded flex items-center gap-4 text-xs border border-slate-600">
          <div className="header_stat_total_rows flex flex-col leading-none">
            <span className="text-slate-400 text-[9px] uppercase tracking-wider">Total Rows</span>
            <span className="font-mono font-bold text-white text-sm">{statsTotalRows}</span>
          </div>
          <div className="h-6 w-px bg-slate-600"></div>
          <div className="header_stat_last_update flex flex-col leading-none">
            <span className="text-slate-400 text-[9px] uppercase tracking-wider">Last Update</span>
            <span className="font-mono font-bold text-green-400 text-sm">{statsLastUpdateLabel}</span>
          </div>
        </div>

        <div className="header_stats_bar bg-slate-900/50 px-1 py-1 rounded flex items-center gap-1 text-xs border border-slate-600">

          {/* SEARCH HEADER */}
          <div className="header_search_header relative">
            <input type="text"
              value={headerSearchTerm}
              onChange={(e) => { setHeaderSearchTerm(e.target.value); setHeaderSearchOpen(true); }}
              onFocus={() => setHeaderSearchOpen(true)}
              placeholder="search header"
              className="bg-slate-800 border border-slate-600 rounded px-2 py-1 text-xs text-white placeholder-slate-400 focus:outline-none focus:border-blue-500 w-32 focus:w-56 transition-all"
            />
            {headerSearchOpen && headerSearchTerm && (
              <div className="header_search_header_transition absolute top-full left-0 mt-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded shadow-xl max-h-60 overflow-y-auto z-50">
                {metaColumnList.filter(c => c.toLowerCase().includes(headerSearchTerm.toLowerCase())).map(col => (
                  <button key={col} onClick={() => { action_JumpToColumn(col); setHeaderSearchOpen(false); setHeaderSearchTerm(""); }}
                    className="w-full text-left px-3 py-2 text-xs border-b border-gray-100 dark:border-slate-700 hover:bg-blue-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 block truncate transition-colors">
                    <span>{col}</span>
                  </button>
                ))}
                {metaColumnList.filter(c => c.toLowerCase().includes(headerSearchTerm.toLowerCase())).length === 0 && (
                  <div className="px-3 py-2 text-xs text-gray-400 italic">No headers found</div>
                )}
              </div>
            )}
          </div>

          <div className="header_view_toggles bg-slate-700 p-0.5 rounded flex gap-1">
            <button onClick={() => setViewModeState('grid')}
              className={`header_toggle_grid_btn px-3 py-1 rounded text-xs font-bold transition flex items-center gap-1 ${viewModeState === 'grid' ? 'bg-blue-600 text-white shadow' : 'text-gray-300 hover:bg-slate-600'}`}>
              <span>▦</span> Grid
            </button>
            <button onClick={() => setViewModeState('dashboard')}
              className={`header_toggle_dashboard_btn px-3 py-1 rounded text-xs font-bold transition flex items-center gap-1 ${viewModeState === 'dashboard' ? 'bg-blue-600 text-white shadow' : 'text-gray-300 hover:bg-slate-600'}`}>
              <span>📊</span> Dashboard
            </button>
          </div>

          <div className="header_translation_controls bg-slate-700 p-0.5 rounded flex gap-1">
            <button onClick={() => setIsTranslationActive(false)}
              className={`header_btn_raw_numbers px-2 py-1 rounded text-[12px] font-bold transition flex items-center gap-1 ${!isTranslationActive ? 'bg-blue-600 text-white shadow' : 'text-gray-400 hover:text-white hover:bg-slate-600'}`}>
              Raw
            </button>
            <button onClick={() => setIsTranslationActive(true)}
              className={`header_btn_translated_text px-2 py-1 rounded text-[12px] font-bold transition flex items-center gap-1 ${isTranslationActive ? 'bg-blue-600 text-white shadow' : 'text-gray-400 hover:text-white hover:bg-slate-600'}`}>
              Text
            </button>
          </div>

          <div className="header_calc_controls bg-slate-700 p-0.5 rounded flex gap-1">
            <button onClick={() => { setViewModeState('dashboard'); calculateDashboardStatsFromAPI(); }}
              className="header_btn_calculate bg-blue-600 text-white shadow px-2 py-1 rounded text-[12px] font-bold transition flex items-center gap-1">
              calculate
            </button>
          </div>
        </div>
      </div>

      <div className="header_right_group flex items-center gap-4">
        <button onClick={ui_ToggleDarkMode} className="header_btn_theme_toggle p-1.5 rounded hover:bg-slate-700 text-yellow-400 transition border border-transparent hover:border-slate-600">
          {isDarkModeEnabled ? '☾' : '☼'}
        </button>
        <div className="h-6 w-px bg-slate-700"></div>
        <a href="/login" className="header_btn_logout flex items-center gap-2 text-xs font-bold text-red-400 hover:text-red-300 transition bg-red-950/30 border border-red-900/50 px-3 py-1.5 rounded hover:bg-red-900/50">
          <span>🚪</span> Logout
        </a>
      </div>
    </div>
  );
}
