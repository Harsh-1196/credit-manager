import React from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export interface TableProps extends React.TableHTMLAttributes<HTMLTableElement> {
  dense?: boolean;
}

const BaseTable: React.FC<TableProps> = ({
  className,
  dense = false,
  children,
  ...props
}) => {
  return (
    <div className="w-full overflow-x-auto border border-border rounded-lg bg-surface">
      <table
        className={twMerge(
          clsx(
            "w-full text-left text-sm text-ink border-collapse",
            dense ? "[&_td]:py-2 [&_th]:py-2" : "[&_td]:py-3.5 [&_th]:py-3",
            className
          )
        )}
        {...props}
      >
        {children}
      </table>
    </div>
  );
};

export const TableHeader: React.FC<React.HTMLAttributes<HTMLTableSectionElement>> = ({
  className,
  children,
  ...props
}) => (
  <thead
    className={twMerge(
      clsx(
        "bg-surface-sunken border-b border-border text-xs font-medium text-ink-muted uppercase tracking-wider sticky top-0",
        className
      )
    )}
    {...props}
  >
    {children}
  </thead>
);

export const TableBody: React.FC<React.HTMLAttributes<HTMLTableSectionElement>> = ({
  className,
  children,
  ...props
}) => (
  <tbody
    className={twMerge(clsx("divide-y divide-border bg-surface", className))}
    {...props}
  >
    {children}
  </tbody>
);

export const TableRow: React.FC<React.HTMLAttributes<HTMLTableRowElement>> = ({
  className,
  children,
  ...props
}) => (
  <tr
    className={twMerge(
      clsx(
        "transition-colors hover:bg-surface-sunken/50",
        className
      )
    )}
    {...props}
  >
    {children}
  </tr>
);

export interface TableHeadProps extends React.ThHTMLAttributes<HTMLTableCellElement> {
  align?: "left" | "right" | "center";
}

export const TableHead: React.FC<TableHeadProps> = ({
  className,
  align = "left",
  children,
  ...props
}) => (
  <th
    className={twMerge(
      clsx(
        "px-4 font-semibold text-ink-muted",
        align === "right" && "text-right",
        align === "center" && "text-center",
        align === "left" && "text-left",
        className
      )
    )}
    {...props}
  >
    {children}
  </th>
);

export interface TableCellProps extends React.TdHTMLAttributes<HTMLTableCellElement> {
  align?: "left" | "right" | "center";
  numeric?: boolean;
}

export const TableCell: React.FC<TableCellProps> = ({
  className,
  align = "left",
  numeric = false,
  children,
  ...props
}) => (
  <td
    className={twMerge(
      clsx(
        "px-4 text-ink align-middle",
        numeric && "tabular-nums",
        align === "right" && "text-right",
        align === "center" && "text-center",
        align === "left" && "text-left",
        className
      )
    )}
    {...props}
  >
    {children}
  </td>
);

export type TableComponent = React.FC<TableProps> & {
  Header: typeof TableHeader;
  Body: typeof TableBody;
  Row: typeof TableRow;
  Head: typeof TableHead;
  Cell: typeof TableCell;
};

const CompoundTable = BaseTable as TableComponent;
CompoundTable.Header = TableHeader;
CompoundTable.Body = TableBody;
CompoundTable.Row = TableRow;
CompoundTable.Head = TableHead;
CompoundTable.Cell = TableCell;

export { CompoundTable as Table };
