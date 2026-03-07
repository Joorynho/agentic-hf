# Data Hubs Design Guide
## Bloomberg Terminal Aesthetics for Mission Control

### Design Philosophy

The four data hubs follow a unified design language emphasizing:
- **Information Density**: Maximum data per pixel, minimal wasted space
- **Precision**: Monospace fonts, high-contrast colors, no decorative gradients
- **Actionability**: Status immediately visible, thresholds clearly marked
- **Institutional Style**: Bloomberg Terminal inspiration with dark theme

---

## Color Palette Reference

| Role | Hex | Usage | Tailwind |
|------|-----|-------|----------|
| Primary BG | `#0b0f14` | Main background | `bg-gray-950` |
| Secondary BG | `#1a1f2e` | Cards, headers | `bg-gray-900` |
| Text Primary | `#ffffff` | Main text | `text-white` |
| Text Secondary | `#a0aec0` | Labels, descriptions | `text-text-secondary` |
| Text Tertiary | `#718096` | Timestamps, metadata | `text-text-tertiary` |
| Border | `#4a5568` | Lines, separators | `border-steel-blue` |
| Accent (Cyan) | `#00d9ff` | Headers, focus | `text-accent-cyan` |
| Accent (Red) | `#ff4757` | Negative, alerts | `text-accent-red` |
| Accent (Green) | `#2ed573` | Positive, active | `text-green-400` |

### No Gradients Rule
All UI elements use **solid colors only**. Examples:
- ✅ `bg-bg-secondary` (solid)
- ❌ `bg-gradient-to-r` (forbidden)

---

## Typography Scale

```
h1: text-xl font-bold           (20px, bold, titles)
h2: text-lg font-bold           (18px, bold, section headers)
h3: text-sm font-bold           (14px, bold, subsection headers)
label: text-xs uppercase        (12px, uppercase, field labels)
body: text-sm                   (14px, regular, prose)
small: text-xs                  (12px, regular, metadata)
mono: font-mono                 (all numbers, timestamps, IDs)
```

All fonts should be **JetBrains Mono** or fallback to Courier New:
```css
font-family: "JetBrains Mono", "Courier New", monospace;
```

---

## Component Patterns

### 1. Table Header Pattern
```tsx
<thead className="sticky top-0 bg-bg-secondary">
  <tr className="border-b border-steel-blue">
    <th className="text-left py-2 px-2 text-text-secondary font-normal">Column Name</th>
    <!-- More columns -->
  </tr>
</thead>
```

**Key Points:**
- `sticky top-0`: Scrolling still visible
- `bg-bg-secondary`: Slightly lighter background
- `border-b border-steel-blue`: Clean line separator
- `py-2 px-2`: 16px/8px padding for tight spacing
- `text-text-secondary`: Muted color for labels

### 2. Table Row Pattern
```tsx
<tr className="border-b border-steel-blue hover:bg-bg-secondary transition-colors">
  <td className="py-1 px-2 text-text-primary">{value}</td>
</tr>
```

**Key Points:**
- `py-1`: Minimal 8px vertical padding
- `hover:bg-bg-secondary`: Subtle hover effect
- `transition-colors`: Smooth color change on hover
- `border-b`: Separator between rows

### 3. Status Badge Pattern
```tsx
<span className={`px-2 py-0.5 rounded text-xs inline-block ${
  status === 'ACTIVE'
    ? 'bg-green-900/40 text-green-400 border border-green-700'
    : 'bg-accent-red/40 text-accent-red border border-accent-red'
}`}>
  {status}
</span>
```

**Key Points:**
- `bg-XX/40`: Semi-transparent background (40% opacity)
- `text-XX-400`: Bright color for contrast
- `border border-XX-700`: Matching border color
- `inline-block`: Only as wide as content

### 4. Chart Container Pattern
```tsx
<div className="bg-bg-secondary rounded border border-steel-blue p-2">
  <div className="text-xs text-text-secondary mb-1 font-mono uppercase">Chart Title</div>
  <ResponsiveContainer width="100%" height="100%">
    {/* Recharts chart component */}
  </ResponsiveContainer>
</div>
```

**Key Points:**
- `bg-bg-secondary`: Subtle background
- `border border-steel-blue`: Frame the chart
- `p-2`: Compact 8px padding
- `text-xs uppercase`: Label above chart
- Responsive container with 100% dimensions

### 5. Alert Pattern
```tsx
<div className={`text-xs font-mono py-1 px-2 rounded border ${
  alert.severity === 'CRITICAL'
    ? 'bg-accent-red/20 border-accent-red text-accent-red'
    : 'bg-yellow-900/20 border-yellow-700 text-yellow-300'
}`}>
  <div className="flex justify-between items-start gap-2">
    <span className="flex-shrink-0">{pod_id}</span>
    <span className="flex-1">{message}</span>
    <span className="text-text-tertiary text-xs flex-shrink-0">{timestamp}</span>
  </div>
  <div className="text-text-tertiary mt-0.5">Metric: {value} (limit: {threshold})</div>
</div>
```

**Key Points:**
- Semantic coloring based on severity
- Multi-line with justified layout
- Timestamp right-aligned
- Secondary details in smaller, muted text

---

## Specific Hub Layouts

### Performance Hub
```
┌─────────────────────────────────────────┐
│ PERFORMANCE SUMMARY                     │
├─────────────────────────────────────────┤
│ Pod │ NAV │ Daily P&L │ ... │ Status   │
├─────┼─────┼───────────┼─────┼──────────┤
│ ALPH│ 1.2M│  +50K     │ ... │ ACTIVE   │
│ BETA│ 980K│  -30K     │ ... │ HALTED   │
├─────────────────────────────────────────┤
│ [NAV Curve Chart] │ [Returns Histogram] │
└─────────────────────────────────────────┘
```

**Dimensions:**
- Table takes 50% of hub height
- Charts split remaining height in 50/50
- All components have 2px padding
- Borders between sections

### Risk Hub
```
┌─────────────────────────────────────────┐
│ RISK DASHBOARD                          │
├─────────────────────────────────────────┤
│ Pod │ Vol % │ VaR │ Leverage │ Status  │
├─────┼───────┼─────┼──────────┼─────────┤
│ ALPH│ 18.2% │ 0.03│   1.8x   │ OK      │
│ BETA│ 22.1% │ 0.04│   2.3x   │ BREACH  │
├─────────────────────────────────────────┤
│ SECTOR EXPOSURE                         │
│ ALPH │ [████░░░░░░][████░░░░░░]...      │
│ BETA │ [███░░░░░░░][██░░░░░░░░]...      │
├─────────────────────────────────────────┤
│ RECENT ALERTS (max-h-48)                │
│ [⚠] BETA Leverage exceeded (2.3x)       │
│ [⚠] ALPH Drawdown warning (4.2%)        │
└─────────────────────────────────────────┘
```

**Key Features:**
- Risk metrics table with breach highlighting
- Heatmap with opacity gradients (0-1)
- Scrollable alert log with color coding

### Execution Hub
```
┌─────────────────────────────────────────┐
│ EXECUTION DESK                          │
├─────────────────────────────────────────┤
│ Notional  │ Fills/Min │ Slippage │ Trades│
│ $2.1M     │    5.2    │  +$12.5  │  47   │
├─────────────────────────────────────────┤
│ Filled: 40 (85%)│ Partial: 5 (10%)│ Pend: 2│
├─────────────────────────────────────────┤
│ Time  │ Pod  │ Symbol│ Side│ Qty │Price  │
├───────┼──────┼───────┼─────┼─────┼───────┤
│14:32:1│ALPHA │AAPL   │BUY  │100  │$150.45│
│14:31:5│BETA  │MSFT   │SELL │200  │$370.12│
│...    │...   │...    │...  │...  │...    │
└─────────────────────────────────────────┘
```

**Key Features:**
- 4-column stats cards at top
- Order status breakdown
- 30-row scrollable trade table
- Real-time P&L calculation

### Governance Hub
```
┌─────────────────────────────────────────┐
│ GOVERNANCE CONTROL                      │
├─────────────────────────────────────────┤
│CIO_MANDATE│CRO_CONSTRAINT│CEO_OVR│AUDIT│
│     3     │      2       │   0   │  1   │
├─────────────────────────────────────────┤
│[Pie Chart: Pod Allocations] │[Bar Chart]│
│ ALPHA: 28%                  │ 3 CIO    │
│ BETA:  22%                  │ 2 CRO    │
│ GAMMA: 18%                  │ 1 AUDIT  │
├─────────────────────────────────────────┤
│ GOVERNANCE EVENTS (max-h-48)            │
│ [CIO_MANDATE] 14:30 +5% TECH            │
│ [CRO_CONST]   14:20 Leverage 1.5x       │
│ [AUDIT]       14:10 Compliance check OK │
└─────────────────────────────────────────┘
```

**Key Features:**
- Event type statistics at top
- 50/50 split between pie and bar charts
- Timeline of recent governance decisions
- Color-coded by event type

---

## Responsive Behavior

### Desktop (Full Width)
- All components display at full resolution
- Charts render at optimal size (height from flex container)
- Tables show all columns without wrapping

### Tablet (Right Panel Only)
- Tab navigation becomes compact (2-line)
- Chart height reduced but still visible
- Table font size reduced to maintain readability

### Mobile (Not Supported)
These hubs are designed for desktop/trading terminal use only.
Target: 1920x1080+ minimum, typically 1/3 width in 3-column layout.

---

## Animation Standards

**Permitted Animations:**
- `transition-colors`: Hover state color changes (200ms)
- `hover:bg-XX`: Subtle background highlight on interaction
- Chart re-render on data change (Recharts default)

**Forbidden Animations:**
- ❌ Floating animations
- ❌ Entrance transitions (fade, slide)
- ❌ Pulsing/breathing effects (except status indicators)
- ❌ Particle effects
- ❌ 3D transforms

**Bloomberg Rule:** Institutional traders prefer crisp, immediate visual feedback.
Animations should be < 200ms and only on user interaction.

---

## Data Density Principles

### Space Efficiency
```
Padding:  py-1 px-2 = 8px vertical, 16px horizontal
Gap:      gap-2 = 8px between flex items
Border:   1px solid only
Margins:  Minimal, only between distinct sections
```

### Text Formatting
```
Numbers:  Right-aligned, monospace font, no thousand separators
Currency: Prefixed with $, 2-4 decimal places based on context
Percent:  Suffixed with %, 1-2 decimal places
Time:     HH:MM:SS format, right-aligned, small font
Status:   ALL CAPS, no abbreviations
```

### Table Guidelines
- Minimum column width: 60px (medium width)
- Maximum rows visible: 30 before scroll
- Header always sticky on scroll
- Hover state on entire row, not individual cells

---

## Accessibility Notes

### Color Contrast
- Text: 7:1 contrast ratio (AAA WCAG)
- Borders: 4.5:1 minimum
- Not relying on color alone for status (use text too)

### Keyboard Navigation
- Tab through table rows (not implemented in MVP but supported by structure)
- Status indicators readable in screen readers (span with class, not just color)
- All interactive elements have visible focus states

### Readability
- Minimum font size: 12px (no smaller)
- Line height: 1.5 (default, supports breathing room)
- Sufficient whitespace around dense tables

---

## Testing Checklist

- [ ] All colors render correctly on calibrated displays
- [ ] No gradients visible in any component
- [ ] Monospace fonts load and render properly
- [ ] Table headers sticky while scrolling
- [ ] Charts responsive to parent container resize
- [ ] Hover states appear on all interactive elements
- [ ] Status colors visible in different lighting conditions
- [ ] Font sizes readable at 20"/1920px distance (typical trader setup)
- [ ] No performance lag with 50+ rows of data
- [ ] Alert timestamps accurate to HH:MM:SS
- [ ] Number formatting consistent ($ prefix, decimal places)

---

## Future Enhancement Ideas

1. **Heatmap Clustering**: Group similar-performing pods in Performance Hub
2. **Risk Correlation Matrix**: Visual correlation between pod risks
3. **Order Flow Visualization**: Animated paths from pods to execution in Execution Hub
4. **Governance Approval Flow**: Visual state machine for mandate approval process
5. **Custom Alerting**: User-configurable thresholds with visual alerts
6. **Dark Mode Toggle**: (Already dark, but could add light mode option)
7. **Data Export**: CSV/JSON export buttons on each hub
8. **Fullscreen Charts**: Click chart to expand to full view
9. **Metric Comparisons**: Year-to-date, month-to-date views
10. **Real-time Notifications**: Toast/badge alerts for critical events
