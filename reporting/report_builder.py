"""Human-readable report that preserves uncertainty and run completeness."""

from __future__ import annotations


def _safe(value) -> str:
    return str(value if value is not None else "unknown").replace("\n", " ").replace("|", "\\|")


def build_report(resources: list[dict], manifest: dict) -> str:
    exposure = manifest.get("priced_exposure_monthly", {})
    total = exposure.get("amount")
    total_text = f"${total:.2f} USD/month" if isinstance(total, (int, float)) else "Unknown (no validated subtotal)"
    lines = [
        "# Azure Waste Hunter — Run Report",
        "",
        f"- Run ID: `{manifest.get('run_id', 'unknown')}`",
        f"- Run status: **{_safe(manifest.get('status'))}**",
        f"- Inventory complete: **{bool(manifest.get('inventory_complete'))}**",
        f"- Estimated monthly cost exposure for reviewed candidates: **{total_text}**",
        f"- Priced candidates: {exposure.get('priced_count', 0)}; unpriced candidates: {exposure.get('unpriced_count', 0)}",
        "",
        "> Estimates are review signals, not verified avoidable spend or realized savings. Unknown prices are excluded from the subtotal.",
        "",
        "## Assessment results",
        "",
    ]
    if not resources:
        lines.append("No resources were returned by discovery.")
    for resource in resources:
        status = resource.get("assessment_status", "unassessed")
        price = resource.get("price", {})
        location = _safe(resource.get("location"))
        lines.extend([
            f"### {_safe(resource.get('type')).upper()} — {_safe(resource.get('name'))}",
            f"- Assessment: **{_safe(status)}** — {_safe(resource.get('assessment_reason'))}",
            f"- Location: {_safe(location)}",
        ])
        coverage = resource.get("metric_coverage")
        if coverage:
            lines.append(f"- Metric coverage: {coverage.get('sample_count', 0)}/{coverage.get('expected_samples', 0)} samples ({coverage.get('coverage', 0):.0%})")
        if price.get("status") == "priced":
            lines.append(f"- Estimated monthly exposure: ${price['amount']:.2f} {price['currency']} ({_safe(price.get('source'))}; {_safe(price.get('unit'))})")
        elif price.get("status") == "not_applicable":
            lines.append("- Price: not estimated; resource was not classified as a review candidate.")
        else:
            lines.append(f"- Price: **unknown** — {_safe(price.get('reason'))}")
        tags = resource.get("tag_assessment", {})
        lines.append(f"- Tag assessment: {_safe(tags.get('status'))}; violations: {_safe(', '.join(tags.get('violations', [])) or 'none')}")
        lines.append("")

    lines.extend(["## Inventory outcomes", ""])
    if manifest.get("inventory"):
        lines.append("| Resource type | Queries | Successful | Discovered |")
        lines.append("|---|---:|---:|---:|")
        for kind, counts in sorted(manifest["inventory"].items()):
            lines.append(f"| {_safe(kind)} | {counts.get('queries_attempted', 0)} | {counts.get('queries_succeeded', 0)} | {counts.get('resources_discovered', 0)} |")
    else:
        lines.append("No inventory outcomes were recorded.")

    lines.extend(["", "## Run errors", ""])
    if manifest.get("errors"):
        for error in manifest["errors"]:
            lines.append(f"- `{_safe(error.get('stage'))}` ({_safe(error.get('category'))}): {_safe(error.get('message'))}")
    else:
        lines.append("None recorded.")
    lines.extend(["", "## Delivery", "", f"- Status at report creation: **{_safe(manifest.get('delivery', {}).get('status'))}**", ""])
    return "\n".join(lines)
