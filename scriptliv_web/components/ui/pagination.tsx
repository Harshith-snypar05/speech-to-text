"use client";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "./index";
import { cn } from "@/lib/utils";

export interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  pageSizeOptions?: number[];
  onPageChange: (newPage: number) => void;
  onPageSizeChange: (newPageSize: number) => void;
  className?: string;
}

export function PaginationControls({
  page,
  pageSize,
  total,
  pageSizeOptions = [10, 20, 30, 40, 50],
  onPageChange,
  onPageSizeChange,
  className,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const current = Math.min(Math.max(1, page), totalPages);

  const startItem = total === 0 ? 0 : (current - 1) * pageSize + 1;
  const endItem = Math.min(total, current * pageSize);

  // Generate page numbers with ellipsis
  const getPageNumbers = () => {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, i) => i + 1);
    }
    if (current <= 4) {
      return [1, 2, 3, 4, 5, "...", totalPages];
    }
    if (current >= totalPages - 3) {
      return [1, "...", totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
    }
    return [1, "...", current - 1, current, current + 1, "...", totalPages];
  };

  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-t border-line text-sm text-ink-2",
        className
      )}
    >
      {/* Left side: range & page size selector */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs sm:text-sm">
          Showing <span className="font-semibold text-ink">{startItem}</span>–
          <span className="font-semibold text-ink">{endItem}</span> of{" "}
          <span className="font-semibold text-ink">{total}</span>
        </span>

        <div className="flex items-center gap-1.5 text-xs">
          <span>Rows per page:</span>
          <select
            value={pageSize}
            onChange={(e) => {
              const size = Number(e.target.value);
              onPageSizeChange(size);
              onPageChange(1);
            }}
            className="rounded-lg border border-line bg-surface px-2 py-1 text-xs font-medium text-ink focus:border-primary focus:outline-none"
            aria-label="Rows per page"
          >
            {pageSizeOptions.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Right side: Prev, Next & Page Number buttons */}
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          disabled={current <= 1}
          onClick={() => onPageChange(current - 1)}
          className="h-8 px-2 text-xs"
          aria-label="Previous page"
        >
          <ChevronLeft className="size-4" />
        </Button>

        <div className="hidden sm:flex items-center gap-1">
          {getPageNumbers().map((p, idx) =>
            typeof p === "number" ? (
              <button
                key={p}
                onClick={() => onPageChange(p)}
                className={cn(
                  "size-8 rounded-lg text-xs font-medium transition-colors",
                  p === current
                    ? "bg-primary text-white font-semibold shadow-sm"
                    : "text-ink-2 hover:bg-surface-alt hover:text-ink"
                )}
                aria-current={p === current ? "page" : undefined}
              >
                {p}
              </button>
            ) : (
              <span key={`ellipsis-${idx}`} className="px-1 text-xs text-ink-3">
                ...
              </span>
            )
          )}
        </div>

        <span className="sm:hidden text-xs px-2 font-medium text-ink">
          {current} / {totalPages}
        </span>

        <Button
          variant="outline"
          size="sm"
          disabled={current >= totalPages}
          onClick={() => onPageChange(current + 1)}
          className="h-8 px-2 text-xs"
          aria-label="Next page"
        >
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}

