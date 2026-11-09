import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';

interface BreadcrumbsProps {
  customCrumbs?: Array<{ label: string; href?: string }>;
}

export const Breadcrumbs: React.FC<BreadcrumbsProps> = ({ customCrumbs }) => {
  const location = useLocation();

  if (customCrumbs && customCrumbs.length > 0) {
    return (
      <nav aria-label="Breadcrumb" className="flex items-center space-x-1.5 text-xs text-[var(--muted-ink)]">
        <Link to="/" className="hover:text-[var(--ink)] transition-colors">
          Home
        </Link>
        {customCrumbs.map((crumb, idx) => (
          <React.Fragment key={idx}>
            <ChevronRight className="w-3.5 h-3.5 text-[var(--border)]" />
            {crumb.href ? (
              <Link to={crumb.href} className="hover:text-[var(--ink)] transition-colors">
                {crumb.label}
              </Link>
            ) : (
              <span className="text-[var(--ink)] font-medium">{crumb.label}</span>
            )}
          </React.Fragment>
        ))}
      </nav>
    );
  }

  const pathnames = location.pathname.split('/').filter((x) => x);

  if (pathnames.length === 0) {
    return (
      <nav aria-label="Breadcrumb" className="text-xs text-[var(--ink)] font-medium">
        Overview
      </nav>
    );
  }

  return (
    <nav aria-label="Breadcrumb" className="flex items-center space-x-1.5 text-xs text-[var(--muted-ink)]">
      <Link to="/" className="hover:text-[var(--ink)] transition-colors">
        Home
      </Link>
      {pathnames.map((value, index) => {
        const to = `/${pathnames.slice(0, index + 1).join('/')}`;
        const isLast = index === pathnames.length - 1;
        const formatted = value.charAt(0).toUpperCase() + value.slice(1);

        return (
          <React.Fragment key={to}>
            <ChevronRight className="w-3.5 h-3.5 text-[var(--border)]" />
            {isLast ? (
              <span className="text-[var(--ink)] font-medium">{formatted}</span>
            ) : (
              <Link to={to} className="hover:text-[var(--ink)] transition-colors">
                {formatted}
              </Link>
            )}
          </React.Fragment>
        );
      })}
    </nav>
  );
};
