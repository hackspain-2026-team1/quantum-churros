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

export function formatSigned(value: number, digits = 2): string {
	return `${value > 0 ? '+' : ''}${formatNumber(value, digits)}`;
}

const RATIO_FEATURES = new Set([
	'cash_margin',
	'cash_margin_3m',
	'cash_margin_6m',
	'cash_margin_change_3m',
	'receivable_open_ratio',
	'receivable_overdue_ratio',
	'payable_overdue_ratio',
	'overdue_change_3m',
	'reconciled_rate',
	'inflow_change_3m'
]);

const DAY_FEATURES = new Set([
	'collection_delay_days',
	'collection_delay_3m',
	'collection_delay_change_3m'
]);

const MONEY_FEATURES = new Set([
	'net_flow_3m',
	'net_flow_6m',
	'net_flow_volatility_6m',
	'inflow_3m',
	'outflow_3m'
]);

export function formatFeatureValue(feature: string, value: number): string {
	if (RATIO_FEATURES.has(feature)) return formatRatio(value);
	if (DAY_FEATURES.has(feature)) return formatDays(value);
	if (MONEY_FEATURES.has(feature)) return formatEuroCompact(value);
	return formatNumber(value, Number.isInteger(value) ? 0 : 2);
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
