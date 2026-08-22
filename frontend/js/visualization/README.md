# Visualization Modules

Reusable JavaScript modules for chart rendering and dashboard layout management.

## Modules

### 1. chart-renderer.js
**Purpose:** Plotly.js chart rendering wrapper

**Features:**
- Render any Plotly chart type (line, bar, pie, scatter, histogram)
- Responsive resizing with ResizeObserver
- Chart update and lifecycle management
- Export charts as images
- Error handling and display
- Batch rendering support

**Usage:**
```javascript
import { chartRenderer } from './chart-renderer.js';

// Render a chart
await chartRenderer.renderChart('chart-container', plotlySpec);

// Update chart
chartRenderer.updateChart('chart-container', { data: newData });

// Clear chart
chartRenderer.clearChart('chart-container');

// Export as image
const imageUrl = await chartRenderer.exportChart('chart-container', { format: 'png' });
```

**API:**
- `renderChart(containerId, plotlySpec, options)` - Render Plotly chart
- `updateChart(containerId, updates)` - Update existing chart
- `resizeChart(containerId)` - Trigger responsive resize
- `clearChart(containerId)` - Destroy chart
- `getChartSpec(containerId)` - Get chart configuration
- `exportChart(containerId, options)` - Export as image
- `renderMultipleCharts(chartConfigs)` - Batch render
- `createSimpleChart(containerId, data, chartType, options)` - Quick chart creation

---

### 2. dashboard-layout.js
**Purpose:** Grid-based dashboard layout system

**Features:**
- Multiple layout modes (1-col, 2-col, 3-col, grid)
- Dynamic chart add/remove
- Chart sizing (small, medium, large, full-width)
- Responsive grid layout
- Chart controls (fullscreen, remove)
- Layout persistence (save/load config)
- Empty state display

**Usage:**
```javascript
import { initDashboardLayout } from './dashboard-layout.js';

// Initialize dashboard
const dashboard = initDashboardLayout('dashboard-container', {
    layout: 'grid',
    enableRemove: true,
    enableFullscreen: true
});

// Add chart
await dashboard.addChart({
    title: 'Sales Trend',
    plotlySpec: { data: [...], layout: {...} },
    size: 'medium'
});

// Remove chart
dashboard.removeChart('chart-1');

// Change layout
dashboard.setLayout('2-col');

// Save configuration
const config = dashboard.getDashboardConfig();

// Load configuration
await dashboard.loadDashboardConfig(config);
```

**API:**
- `addChart(chartConfig)` - Add chart to dashboard
- `removeChart(chartId)` - Remove chart
- `updateChart(chartId, updates)` - Update chart title/data
- `setLayout(layoutMode)` - Change grid layout
- `toggleFullscreen(chartId)` - Fullscreen mode
- `clearDashboard()` - Remove all charts
- `getDashboardConfig()` - Get save-ready config
- `loadDashboardConfig(config)` - Restore from config
- `resizeAllCharts()` - Trigger resize on all charts
- `showEmptyState()` - Display empty state message

**Layout Modes:**
- `1-col` - Single column (stacked)
- `2-col` - 2 columns on medium+ screens
- `3-col` - 3 columns on large screens
- `grid` - Responsive grid (2-3 columns based on screen)

**Chart Sizes:**
- `small` - 1 column width
- `medium` - 1 column width (default)
- `large` - 2 columns width
- `full` - Full row width

---

## Integration with Pages

### Query Page (query.html)
```javascript
// Inline chart rendering in query results
import { chartRenderer } from './visualization/chart-renderer.js';

function displayResults(response) {
    await chartRenderer.renderChart('chart-display', response.plotly_spec);
}
```

### Dashboard Builder (dashboard.html)
```javascript
// Full dashboard with multiple charts
import { initDashboardLayout } from './visualization/dashboard-layout.js';

const dashboard = initDashboardLayout('dashboard-grid', { layout: 'grid' });

// Add charts from saved queries or API
await dashboard.addChart({ title: 'Chart 1', plotlySpec: spec1 });
await dashboard.addChart({ title: 'Chart 2', plotlySpec: spec2 });
```

---

## Dependencies

- **Plotly.js 2.26+** (via CDN in HTML)
- **Tailwind CSS 3.0+** (for styling)
- Modern browser with ES6 module support

---

## File Structure

```
frontend/js/visualization/
├── chart-renderer.js      (380 lines) - Plotly wrapper
├── dashboard-layout.js    (420 lines) - Grid layout system
└── README.md             (this file)
```

---

## CSS Requirements

Add to `main.css` or `components.css`:

```css
/* Dashboard Grid */
.dashboard-grid {
    display: grid;
    width: 100%;
}

/* Chart Card */
.chart-card {
    transition: box-shadow 0.2s;
}

.chart-card:hover {
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
}

/* Chart Controls */
.btn-icon {
    padding: 0.5rem;
    border-radius: 0.375rem;
    transition: background-color 0.2s;
}

.btn-icon:hover {
    background-color: rgba(0, 0, 0, 0.05);
}

/* Fullscreen Mode */
.chart-wrapper:fullscreen {
    background: white;
    padding: 2rem;
}

.chart-wrapper:fullscreen .chart-canvas {
    height: calc(100vh - 120px);
}
```

---

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

**Required Features:**
- ES6 Modules
- ResizeObserver API
- Fullscreen API
- CSS Grid

---

## Testing

Test chart renderer:
```javascript
// Test rendering
const testSpec = {
    data: [{ type: 'scatter', x: [1, 2, 3], y: [4, 5, 6], mode: 'lines+markers' }],
    layout: { title: 'Test Chart' }
};
await chartRenderer.renderChart('test-container', testSpec);

// Test update
chartRenderer.updateChart('test-container', { 
    layout: { title: 'Updated Chart' } 
});

// Test cleanup
chartRenderer.clearChart('test-container');
```

Test dashboard layout:
```javascript
// Test dashboard
const dashboard = initDashboardLayout('test-dashboard');
await dashboard.addChart({ title: 'Chart 1', plotlySpec: spec1 });
await dashboard.addChart({ title: 'Chart 2', plotlySpec: spec2 });

// Test layout change
dashboard.setLayout('2-col');

// Test persistence
const config = dashboard.getDashboardConfig();
dashboard.clearDashboard();
await dashboard.loadDashboardConfig(config);
```

---

## Future Enhancements

- [ ] Drag-and-drop chart reordering
- [ ] Chart resize handles
- [ ] Dashboard templates
- [ ] Export dashboard as PDF
- [ ] Collaborative editing
- [ ] Real-time chart updates
- [ ] Chart animation controls
- [ ] Accessibility improvements (ARIA labels)

---

**Created:** March 5, 2026 (Day 5 - Task 1)  
**Lines of Code:** ~800 lines total  
**Status:** ✅ Production Ready
