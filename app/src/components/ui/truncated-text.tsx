import { cn } from '@/lib/utils'

interface TruncatedTextProps {
  text: string
  className?: string
  /** Secondary line shown below primary when provided */
  secondary?: string
  as?: 'span' | 'p' | 'div'
}

/** Truncates with ellipsis; full string on hover via native title. */
export function TruncatedText({
  text,
  className,
  secondary,
  as: Tag = 'span',
}: TruncatedTextProps) {
  if (secondary) {
    return (
      <div className={cn('min-w-0', className)}>
        <Tag title={text} className="block truncate">
          {text}
        </Tag>
        <span title={secondary} className="block truncate text-xs text-muted-foreground">
          {secondary}
        </span>
      </div>
    )
  }

  return (
    <Tag title={text} className={cn('block truncate min-w-0', className)}>
      {text}
    </Tag>
  )
}
