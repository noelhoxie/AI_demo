interface Props {
  variant: 'pass' | 'fail' | 'pending' | 'info' | 'critical' | 'high' | 'medium' | 'low'
  children: React.ReactNode
  className?: string
}

const CLASSES: Record<Props['variant'], string> = {
  pass:     'bg-emerald-50 text-emerald-700 border-emerald-200',
  fail:     'bg-red-50 text-red-700 border-red-200',
  pending:  'bg-amber-50 text-amber-700 border-amber-200',
  info:     'bg-blue-50 text-blue-700 border-blue-200',
  critical: 'bg-red-50 text-red-700 border-red-200',
  high:     'bg-orange-50 text-orange-700 border-orange-200',
  medium:   'bg-amber-50 text-amber-700 border-amber-200',
  low:      'bg-slate-100 text-slate-600 border-slate-200',
}

export default function Badge({ variant, children, className = '' }: Props) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${CLASSES[variant]} ${className}`}>
      {children}
    </span>
  )
}
