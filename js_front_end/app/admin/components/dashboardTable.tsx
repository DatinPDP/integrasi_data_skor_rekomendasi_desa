"use client";

import DashboardTh from './resizableTh';
import { useAdminLogic } from '../hooks/useAdminLogic';

type DashboardTableProps = Pick<ReturnType<typeof useAdminLogic>, 'isDarkModeEnabled' | 'dashboardData' | 'isDashboardCalculated'>;

export default function DashboardTable({ isDarkModeEnabled, dashboardData, isDashboardCalculated }: DashboardTableProps) {
  return (
    <div className={`dashboard_table_wrapper dashboard-container shadow-md rounded 
              ${isDarkModeEnabled ? 'bg-slate-800 border-slate-700' : 'bg-white border-gray-200'}`}>
      <table className="dash-table">
        <thead>
          <tr>
            <DashboardTh className="col-no" rowSpan={2}>NO</DashboardTh>
            <DashboardTh className="col-dimensi" rowSpan={2}>DIMENSI</DashboardTh>
            <DashboardTh className="col-sub_dimensi" rowSpan={2}>SUB DIMENSI</DashboardTh>
            <DashboardTh className="col-indikator" rowSpan={2}>INDIKATOR</DashboardTh>
            <DashboardTh className="col-item" rowSpan={2}>ITEM</DashboardTh>
            <th colSpan={6}>SKOR</th>
            <DashboardTh className="col-intervensi" rowSpan={2}>INTERVENSI</DashboardTh>
            <th colSpan={5}>PELAKSANA</th>
          </tr>
          <tr>
            {["Rata-Rata", "1", "2", "3", "4", "5"].map(h => <th key={h} className="col-score">{h}</th>)}
            <DashboardTh className="col-pusat">PUSAT</DashboardTh>
            <DashboardTh className="col-prov">PROV</DashboardTh>
            <DashboardTh className="col-kab">KAB</DashboardTh>
            <DashboardTh className="col-desa">DESA</DashboardTh>
            <DashboardTh className="col-lain">LAIN</DashboardTh>
          </tr>
        </thead>
        <tbody>
          {dashboardData.map((row, idx) => (
            <tr key={idx}>
              {["NO", "DIMENSI", "SUB DIMENSI", "INDIKATOR"].map(k => {
                // @ts-expect-error error_dashboard
                const span = row._rowSpans[k];
                if (span === -1) return null;
                return (
                  <td key={k} className="merged-cell" rowSpan={span > 1 ? span : 1}>
                    {row[k]}
                  </td>
                );
              })}

              <td style={{ padding: '6px', border: '1px solid #ccc' }}>
                {row["ITEM"]}
              </td>

              {/* SCORE COLS */}
              {["SKOR Rata-Rata", "SKOR 1", "SKOR 2", "SKOR 3", "SKOR 4", "SKOR 5"].map(k => (
                <td key={k} style={{ textAlign: 'center' }}>{row[k]}</td>
              ))}

              {/* PELAKSANA */}
              {["INTERVENSI KEGIATAN", "INTERVENSI KEGIATAN", "PELAKSANA KEGIATAN PUSAT", "PELAKSANA KEGIATAN PROVINSI", "PELAKSANA KEGIATAN KABUPATEN", "PELAKSANA KEGIATAN DESA", "PELAKSANA KEGIATAN Lainnya"].map((k, i) => {
                if (i === 0) return null;
                return <td key={i} style={{ whiteSpace: 'pre-wrap', padding: '6px' }}>{row[k]}</td>
              })}
            </tr>
          ))}
          {!isDashboardCalculated && (
            <tr><td colSpan={20} className="text-center p-10 text-gray-400 italic">Click Calculate to generate dashboard</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
