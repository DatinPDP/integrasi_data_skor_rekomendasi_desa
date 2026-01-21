"use client";

import React, { useRef } from 'react';

const DashboardTh = ({
  children,
  className,
  rowSpan,
  colSpan,
  minWidth = 30
}: {
  children: React.ReactNode,
  className?: string,
  rowSpan?: number,
  colSpan?: number,
  minWidth?: number
}) => {
  const thRef = useRef<HTMLTableCellElement>(null);

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation(); // Stop bubbling

    const th = thRef.current;
    if (!th) return;

    const startX = e.pageX;
    const startWidth = th.offsetWidth;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const dx = moveEvent.pageX - startX;
      const newWidth = Math.max(minWidth, startWidth + dx);
      // Force both styles to ensure it sticks
      th.style.width = `${newWidth}px`;
      th.style.minWidth = `${newWidth}px`;
      th.style.maxWidth = `${newWidth}px`;
    };

    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'default';
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    document.body.style.cursor = 'col-resize';
  };

  return (
    <th ref={thRef} className={`relative ${className || ''}`} rowSpan={rowSpan} colSpan={colSpan}>
      {children}
      <div
        className="resizer absolute right-0 top-0 h-full w-1.5 cursor-col-resize hover:bg-blue-500 z-50 bg-transparent"
        onMouseDown={handleMouseDown}
        onClick={(e) => e.stopPropagation()}
      />
    </th>
  );
};

export default DashboardTh;
