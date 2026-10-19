/**
 * CoffeeBeanLogo — SVG coffee bean icon used in navbar and landing page.
 * size: pixel size of the icon (default 24)
 * color: fill color (default warm brown)
 */
export default function CoffeeBeanLogo({ size = 24, color = '#d4a76a' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Outer bean shape */}
      <ellipse
        cx="20" cy="20"
        rx="13" ry="18"
        fill={color}
        transform="rotate(-20 20 20)"
      />
      {/* Inner highlight */}
      <ellipse
        cx="16.5" cy="14"
        rx="5" ry="7"
        fill="rgba(255,255,255,0.15)"
        transform="rotate(-20 16.5 14)"
      />
      {/* Centre crease line */}
      <path
        d="M12 20 Q20 14 28 20"
        stroke="rgba(80,40,10,0.55)"
        strokeWidth="2.2"
        strokeLinecap="round"
        fill="none"
      />
      {/* Second bean overlapping behind — darker */}
      <ellipse
        cx="26" cy="25"
        rx="11" ry="15"
        fill={darken(color, 0.28)}
        transform="rotate(18 26 25)"
      />
      <path
        d="M19 26 Q26 21 33 27"
        stroke="rgba(50,20,5,0.5)"
        strokeWidth="1.8"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  )
}

function darken(hex, amount) {
  // Simple darken by reducing each channel
  const n = parseInt(hex.replace('#', ''), 16)
  const r = Math.max(0, (n >> 16) - Math.round(255 * amount))
  const g = Math.max(0, ((n >> 8) & 0xff) - Math.round(255 * amount))
  const b = Math.max(0, (n & 0xff) - Math.round(255 * amount))
  return `rgb(${r},${g},${b})`
}
