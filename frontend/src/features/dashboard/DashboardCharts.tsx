import React, { useState } from 'react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { formatIndianMoney } from '../../lib/money';
import type { AgingBucketItem, DisbursalVsRepaymentItem, SavingsTrendItem } from '../../lib/api/types';
import { BarChart3, Table as TableIcon } from 'lucide-react';

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    name?: string;
    value?: number | string;
    color?: string;
  }>;
  label?: string;
  isCurrency?: boolean;
}

const CustomChartTooltip: React.FC<CustomTooltipProps> = ({ active, payload, label, isCurrency = true }) => {
  if (!active || !payload || !payload.length) return null;

  return (
    <div className="bg-[var(--surface)] text-[var(--ink)] border border-[var(--border)] rounded px-3 py-2 text-xs shadow-md">
      <p className="font-semibold mb-1 text-[var(--ink)]">{label}</p>
      {payload.map((entry, idx) => (
        <div key={idx} className="flex items-center gap-2 text-[var(--muted-ink)]">
          <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ backgroundColor: entry.color }} />
          <span>{entry.name}:</span>
          <span className="font-mono font-semibold text-[var(--ink)]">
            {isCurrency ? formatIndianMoney(entry.value ?? 0) : entry.value}
          </span>
        </div>
      ))}
    </div>
  );
};

/* -------------------------------------------------------------------------- */
/* 1. Savings Trend Chart & Table                                             */
/* -------------------------------------------------------------------------- */
export const SavingsTrendChart: React.FC<{ data: SavingsTrendItem[] }> = ({ data }) => {
  const [viewMode, setViewMode] = useState<'chart' | 'table'>('chart');

  const chartData = data.map((d) => ({
    month: d.month,
    savings: parseFloat(d.amount) || 0,
  }));

  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5 flex flex-col h-full">
      <div className="flex items-center justify-between pb-3 border-b border-[var(--border)] mb-4">
        <div>
          <h3 className="font-serif font-bold text-base text-[var(--ink)]">Savings Growth Trend</h3>
          <p className="text-xs text-[var(--muted-ink)]">Historical cumulative savings over time</p>
        </div>
        <div className="inline-flex rounded-md border border-[var(--border)] p-0.5 bg-[var(--surface-muted)]">
          <button
            type="button"
            onClick={() => setViewMode('chart')}
            className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded ${
              viewMode === 'chart'
                ? 'bg-[var(--surface)] text-[var(--primary)] shadow-sm'
                : 'text-[var(--muted-ink)] hover:text-[var(--ink)]'
            }`}
            aria-label="View as Chart"
          >
            <BarChart3 className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Chart</span>
          </button>
          <button
            type="button"
            onClick={() => setViewMode('table')}
            className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded ${
              viewMode === 'table'
                ? 'bg-[var(--surface)] text-[var(--primary)] shadow-sm'
                : 'text-[var(--muted-ink)] hover:text-[var(--ink)]'
            }`}
            aria-label="View as Accessible Table"
          >
            <TableIcon className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Table</span>
          </button>
        </div>
      </div>

      {viewMode === 'chart' ? (
        <div className="w-full h-64 min-h-[256px]">
          {chartData.length === 0 ? (
            <div className="h-full flex items-center justify-center text-xs text-[var(--muted-ink)]">
              No trend data recorded yet.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
                <defs>
                  <linearGradient id="savingsFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="var(--primary)" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis
                  dataKey="month"
                  stroke="var(--muted-ink)"
                  fontSize={11}
                  tickLine={false}
                  dy={10}
                />
                <YAxis
                  stroke="var(--muted-ink)"
                  fontSize={11}
                  tickLine={false}
                  tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`}
                />
                <Tooltip content={<CustomChartTooltip isCurrency />} />
                <Area
                  type="monotone"
                  dataKey="savings"
                  name="Total Savings"
                  stroke="var(--primary)"
                  strokeWidth={2.5}
                  fillOpacity={1}
                  fill="url(#savingsFill)"
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-[var(--border)] text-[var(--muted-ink)] font-semibold uppercase">
                <th className="py-2 px-3">Period (Month)</th>
                <th className="py-2 px-3 text-right">Cumulative Savings</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {data.map((row) => (
                <tr key={row.month} className="hover:bg-[var(--surface-muted)]">
                  <td className="py-2.5 px-3 font-mono">{row.month}</td>
                  <td className="py-2.5 px-3 text-right font-mono font-semibold">
                    {formatIndianMoney(row.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

/* -------------------------------------------------------------------------- */
/* 2. Loan Aging Buckets Chart & Table                                        */
/* -------------------------------------------------------------------------- */
export const AgingBucketsChart: React.FC<{ data: AgingBucketItem[] }> = ({ data }) => {
  const [viewMode, setViewMode] = useState<'chart' | 'table'>('chart');

  const chartData = data.map((d) => ({
    bucket: d.bucket,
    amount: parseFloat(d.amount) || 0,
    count: d.count,
  }));

  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5 flex flex-col h-full">
      <div className="flex items-center justify-between pb-3 border-b border-[var(--border)] mb-4">
        <div>
          <h3 className="font-serif font-bold text-base text-[var(--ink)]">Portfolio Aging (PAR)</h3>
          <p className="text-xs text-[var(--muted-ink)]">Delinquency distribution across aging tiers</p>
        </div>
        <div className="inline-flex rounded-md border border-[var(--border)] p-0.5 bg-[var(--surface-muted)]">
          <button
            type="button"
            onClick={() => setViewMode('chart')}
            className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded ${
              viewMode === 'chart'
                ? 'bg-[var(--surface)] text-[var(--primary)] shadow-sm'
                : 'text-[var(--muted-ink)] hover:text-[var(--ink)]'
            }`}
            aria-label="View as Chart"
          >
            <BarChart3 className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Chart</span>
          </button>
          <button
            type="button"
            onClick={() => setViewMode('table')}
            className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded ${
              viewMode === 'table'
                ? 'bg-[var(--surface)] text-[var(--primary)] shadow-sm'
                : 'text-[var(--muted-ink)] hover:text-[var(--ink)]'
            }`}
            aria-label="View as Accessible Table"
          >
            <TableIcon className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Table</span>
          </button>
        </div>
      </div>

      {viewMode === 'chart' ? (
        <div className="w-full h-64 min-h-[256px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis
                dataKey="bucket"
                stroke="var(--muted-ink)"
                fontSize={11}
                tickLine={false}
                dy={10}
              />
              <YAxis
                stroke="var(--muted-ink)"
                fontSize={11}
                tickLine={false}
                tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`}
              />
              <Tooltip content={<CustomChartTooltip isCurrency />} />
              <Bar
                dataKey="amount"
                name="Outstanding Principal"
                fill="var(--accent)"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-[var(--border)] text-[var(--muted-ink)] font-semibold uppercase">
                <th className="py-2 px-3">Aging Bracket</th>
                <th className="py-2 px-3 text-right">Outstanding Amount</th>
                <th className="py-2 px-3 text-right">Loan Count</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {data.map((row) => (
                <tr key={row.bucket} className="hover:bg-[var(--surface-muted)]">
                  <td className="py-2.5 px-3 font-medium text-[var(--ink)]">{row.bucket}</td>
                  <td className="py-2.5 px-3 text-right font-mono font-semibold text-[var(--accent)]">
                    {formatIndianMoney(row.amount)}
                  </td>
                  <td className="py-2.5 px-3 text-right font-mono">{row.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

/* -------------------------------------------------------------------------- */
/* 3. Disbursals vs Repayments Chart & Table                                  */
/* -------------------------------------------------------------------------- */
export const DisbursalsVsRepaymentsChart: React.FC<{ data: DisbursalVsRepaymentItem[] }> = ({ data }) => {
  const [viewMode, setViewMode] = useState<'chart' | 'table'>('chart');

  const chartData = data.map((d) => ({
    month: d.month,
    disbursals: parseFloat(d.disbursed) || 0,
    repayments: parseFloat(d.repaid) || 0,
  }));

  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5 flex flex-col h-full">
      <div className="flex items-center justify-between pb-3 border-b border-[var(--border)] mb-4">
        <div>
          <h3 className="font-serif font-bold text-base text-[var(--ink)]">Cash Flow Comparison</h3>
          <p className="text-xs text-[var(--muted-ink)]">Disbursals vs Repayments by month</p>
        </div>
        <div className="inline-flex rounded-md border border-[var(--border)] p-0.5 bg-[var(--surface-muted)]">
          <button
            type="button"
            onClick={() => setViewMode('chart')}
            className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded ${
              viewMode === 'chart'
                ? 'bg-[var(--surface)] text-[var(--primary)] shadow-sm'
                : 'text-[var(--muted-ink)] hover:text-[var(--ink)]'
            }`}
            aria-label="View as Chart"
          >
            <BarChart3 className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Chart</span>
          </button>
          <button
            type="button"
            onClick={() => setViewMode('table')}
            className={`flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded ${
              viewMode === 'table'
                ? 'bg-[var(--surface)] text-[var(--primary)] shadow-sm'
                : 'text-[var(--muted-ink)] hover:text-[var(--ink)]'
            }`}
            aria-label="View as Accessible Table"
          >
            <TableIcon className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">Table</span>
          </button>
        </div>
      </div>

      {viewMode === 'chart' ? (
        <div className="w-full h-64 min-h-[256px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis
                dataKey="month"
                stroke="var(--muted-ink)"
                fontSize={11}
                tickLine={false}
                dy={10}
              />
              <YAxis
                stroke="var(--muted-ink)"
                fontSize={11}
                tickLine={false}
                tickFormatter={(val) => `₹${(val / 1000).toFixed(0)}k`}
              />
              <Tooltip content={<CustomChartTooltip isCurrency />} />
              <Legend
                verticalAlign="top"
                align="right"
                wrapperStyle={{ fontSize: '11px', paddingBottom: '10px' }}
              />
              <Bar
                dataKey="disbursals"
                name="Disbursals"
                fill="var(--accent)"
                radius={[4, 4, 0, 0]}
              />
              <Bar
                dataKey="repayments"
                name="Repayments"
                fill="var(--primary)"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-[var(--border)] text-[var(--muted-ink)] font-semibold uppercase">
                <th className="py-2 px-3">Month</th>
                <th className="py-2 px-3 text-right">Disbursals</th>
                <th className="py-2 px-3 text-right">Repayments</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {data.map((row) => (
                <tr key={row.month} className="hover:bg-[var(--surface-muted)]">
                  <td className="py-2.5 px-3 font-mono">{row.month}</td>
                  <td className="py-2.5 px-3 text-right font-mono font-semibold text-[var(--accent)]">
                    {formatIndianMoney(row.disbursed)}
                  </td>
                  <td className="py-2.5 px-3 text-right font-mono font-semibold text-[var(--primary)]">
                    {formatIndianMoney(row.repaid)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
