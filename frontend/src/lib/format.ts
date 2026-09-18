const NBSP = '\u00A0';

export function formatNumber(value: number, digits = 0): string {
	return new Intl.NumberFormat('es-ES', {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits
	}).format(value);
}

export function formatEuro(value: number, digits = 2): string {
	const sign = value > 0 ? '+' : '';
	return `${sign}${formatNumber(value, digits)}${NBSP}€`;
}

export function formatEuroCompact(value: number): string {
	const absolute = Math.abs(value);
	if (absolute >= 1_000_000) return `${formatNumber(value / 1_000_000, 1)}${NBSP}M€`;
	if (absolute >= 1_000) return `${formatNumber(value / 1_000, 0)}${NBSP}k€`;
	return formatEuro(value);
}

export function formatPercent(ratio: number, digits = 1): string {
	return `${formatNumber(ratio * 100, digits)}${NBSP}%`;
}

export function formatDays(value: number): string {
	return `${formatNumber(value, 0)}${NBSP}días`;
}

export function formatRatio(value: number, digits = 2): string {
	return formatNumber(value, digits);
}

export function formatPeriod(month: string): string {
	const [year, monthNumber] = month.split('-').map(Number);
	return new Intl.DateTimeFormat('es-ES', { month: 'long', year: 'numeric' }).format(
		new Date(year, monthNumber - 1, 1)
	);
}

export function formatAxisMonth(month: string): string {
	const [year, monthNumber] = month.split('-');
	return `${monthNumber}/${year.slice(2)}`;
}
