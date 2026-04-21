---
name: d2-architect-standard
description: Create and manage architecture diagrams using the D2 declarative language. Use when generating, refactoring, or updating architecture diagrams for system components, data flows, or infrastructure.
---

# D2 Architectural Standards

This skill enforces a consistent visual and structural standard for all D2 diagrams.

## Mandatory Configuration

Every `.d2` file must start with this standard configuration block. **Themes must be applied via CLI flag `-t 0` (Neutral), never inside the file.**

```d2
direction: right
vars: {
  d2-config: {
    layout-engine: elk
    sketch: true # Default to true unless 'formal' is requested
  }
}
```

## Branding & UX Standards

### 1. Title (Top Center)
Use a clean Markdown header, positioned at the top center.
```d2
title: |md
  # <Diagram Title>
| {near: top-center}
```

### 2. Watermark (Optional — Top Right)
Add a personal or project watermark if desired:
```d2
watermark: "your-handle" {
  near: top-right
  style: {
    stroke-dash: 3
    font-size: 14
    opacity: 0.6
  }
}
```

## Structural Standards

### 1. Class-Based Styling (DRY)
Do not style individual nodes. Use standard classes for consistency:
```d2
classes: {
  compute_node: { shape: image; width: 48; height: 48 }
  storage_node: { shape: image; width: 48; height: 48 }
  auth_node: { shape: image; width: 48; height: 48 }
  infra_node: { shape: image; width: 48; height: 48 }
}
```

### 2. Icon Management
- **Local Priority:** Always prioritize local icons bundled with your project.
- **Icon Bundling:** Local paths ensure D2 bundles SVGs into a portable file.
- **Fallback:** If no local icon is available, reference a stable public URL.

### 3. Container Rules
- Use nested containers for logical grouping (e.g., GCP → Region → Service).
- **Important:** If a container needs an icon, the icon MUST be a separate child node because image shapes in D2 cannot have children.

## Workflows

### Generating a New Diagram
1. Identify the system components and their relationships.
2. Apply the **Mandatory Configuration**.
3. Set the **Title** (and optional Watermark).
4. Use local icon paths where available.
5. Render with: `d2 -t 0 <input>.d2 <output>.svg`.

### Updating Icons
If a required icon is missing:
1. Search your local icons directory first.
2. If not found, download the SVG from a reliable source before referencing it.
