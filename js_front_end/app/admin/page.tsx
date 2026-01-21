"use client";

import { AgGridReact } from 'ag-grid-react';
import { useAdminLogic } from './hooks/useAdminLogic';
import AdminHeader from './components/adminHeader';
import AdminSidebar from './components/adminSidebar';
import DashboardTable from './components/dashboardTable';

export default function AdminDashboardPage() {
  const logic = useAdminLogic();
  // Destructure values to avoid linter confusion regarding ref access during render
  const {
    gridRef,
    rowData,
    columnDefs,
    viewModeState,
    isDarkModeEnabled,
    dashboardData,
    isDashboardCalculated
  } = logic;

  return (
    <div className="global_body_container font-mono bg-gray-100 h-screen flex flex-col transition-colors duration-300 dark:bg-slate-900 dark:text-slate-100">
      {/* --- HEADER --- */}
      <AdminHeader {...logic} />

      <div className="main_layout_wrapper flex flex-1 overflow-hidden">

        {/* --- SIDEBAR --- */}
        <AdminSidebar {...logic} />

        {/* --- MAIN CONTENT AREA --- */}
        <div className={`main_content_area flex-1 relative overflow-hidden flex flex-col 
          ${isDarkModeEnabled ? 'bg-slate-900' : 'bg-gray-50'}`}>

          {/* VIEW: GRID */}
          <div className={`view_container_grid flex-1 p-0 relative ${viewModeState === 'grid' ? 'block' : 'hidden'}`}>
            <div className="ag-theme-alpine w-full h-full border-none">
              <AgGridReact
                theme="legacy"
                ref={gridRef}
                rowData={rowData}
                columnDefs={columnDefs}
                defaultColDef={{
                  resizable: true,
                  filter: true,
                  sortable: true,
                  minWidth: 100
                }}
                rowSelection="multiple"
                animateRows={false}
              />
            </div>
          </div>

          {/* VIEW: DASHBOARD */}
          <div className={`view_container_dashboard flex-1 p-4 overflow-hidden relative ${viewModeState === 'dashboard' ? 'block' : 'hidden'}`}>
            <DashboardTable
              isDarkModeEnabled={isDarkModeEnabled}
              dashboardData={dashboardData}
              isDashboardCalculated={isDashboardCalculated}
            />
          </div>

        </div>
      </div>
    </div>
  );
}
