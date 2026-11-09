// A few stroke icons drawn inline (no icon package in the driver app). Always decorative: the text next to
// each icon carries the meaning, so they are hidden from screen readers.
const Svg = ({ size = 22, children }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="shrink-0">{children}</svg>
)

export const NavigateIcon = (p) => <Svg {...p}><path d="M3 11 21 3l-8 18-2-8-8-2Z" /></Svg>
export const CheckIcon = (p) => <Svg {...p}><path d="M4 12.5 9.5 18 20 6.5" /></Svg>
export const CrossIcon = (p) => <Svg {...p}><path d="M6 6l12 12M18 6 6 18" /></Svg>
export const CloudOffIcon = (p) => <Svg {...p}><path d="M3 3l18 18" /><path d="M7.5 7.6A5 5 0 0 0 6 17h11m3.2-1.6A4 4 0 0 0 17 9h-.5a6 6 0 0 0-6.9-4.5" /></Svg>
export const CloudIcon = (p) => <Svg {...p}><path d="M17 18H7a5 5 0 1 1 1.2-9.9A6 6 0 0 1 19.6 10 4 4 0 0 1 17 18Z" /></Svg>
export const SyncIcon = (p) => <Svg {...p}><path d="M20 11a8 8 0 0 0-14.3-4.9L4 8" /><path d="M4 3v5h5" /><path d="M4 13a8 8 0 0 0 14.3 4.9L20 16" /><path d="M20 21v-5h-5" /></Svg>
export const CameraIcon = (p) => <Svg {...p}><path d="M4 8h3l2-3h6l2 3h3v11H4Z" /><circle cx="12" cy="13" r="3.5" /></Svg>
export const AlertIcon = (p) => <Svg {...p}><path d="M12 3 2 20h20L12 3Z" /><path d="M12 10v4M12 17.5v.5" /></Svg>
export const ClockIcon = (p) => <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Svg>
