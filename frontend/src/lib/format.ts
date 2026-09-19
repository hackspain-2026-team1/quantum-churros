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

/** Score points held as integer tenths -> '72,4'. The bundle never sends floats for scores. */
export function formatScore(tenths: number): string {
	return formatNumber(tenths / 10, 1);
}

/** Signed score points from integer tenths -> '+1,2' / '-6,1' / '0,0'. */
export function formatScoreDelta(tenths: number): string {
	return new Intl.NumberFormat('es-ES', {
		minimumFractionDigits: 1,
		maximumFractionDigits: 1,
		signDisplay: 'exceptZero'
	}).format(tenths / 10);
}

export function formatSigned(value: number, digits = 0): string {
	return new Intl.NumberFormat('es-ES', {
		minimumFractionDigits: digits,
		maximumFractionDigits: digits,
		signDisplay: 'exceptZero'
	}).format(value);
}

/**
 * Engine sentences quote months as YYYY-MM: 'frente a 2025-09' -> 'frente a septiembre de 2025'.
 * Full dates (YYYY-MM-DD) and months glued to a file name are left as written.
 */
export function humanizeMonths(text: string): string {
	return text.replace(/\b[0-9]{4}-(0[1-9]|1[0-2])\b(?!-[0-9])/g, (month) => formatPeriod(month));
}

/** 'ene 2026' style label for tight spaces (slider ends, chips). */
export function formatPeriodShort(month: string): string {
	const [year, monthNumber] = month.split('-').map(Number);
	return new Intl.DateTimeFormat('es-ES', { month: 'short', year: 'numeric' }).format(
		new Date(year, monthNumber - 1, 1)
	);
}

/** ISO date or date-time -> '1 sept 2026' / '1 sept 2026, 10:30'. */
export function formatTimestamp(value: string): string {
	const hasTime = value.includes('T');
	const date = new Date(hasTime ? value : `${value}T00:00:00`);
	if (Number.isNaN(date.getTime())) return value;
	return new Intl.DateTimeFormat('es-ES', {
		dateStyle: 'medium',
		...(hasTime ? { timeStyle: 'short' } : {})
	}).format(date);
}

/** Short, stable prefix of a content hash for footers and receipts. */
export function shortHash(hash: string, length = 10): string {
	const clean = hash.replace(/^sha256:/, '');
	return clean.length > length ? clean.slice(0, length) : clean;
}

/** Money without a forced plus sign, for balances and evidence rows: '83.281,13 €'. */
export function formatMoney(value: number, digits = 2): string {
	return `${formatNumber(value, digits)}${NBSP}€`;
}

/** Plain quantity: integers stay whole, tiny magnitudes go scientific, the rest keep two decimals. */
export function formatQuantity(value: number): string {
	if (Number.isInteger(value)) return formatNumber(value, 0);
	if (Math.abs(value) < 0.001) {
		return new Intl.NumberFormat('es-ES', {
			notation: 'scientific',
			maximumFractionDigits: 2
		}).format(value);
	}
	return formatNumber(value, 2);
}

/**
 * A bundle value with its unit (profile attributes, evidence rows, receipt metrics).
 * Units: 'EUR' money, 'cuota' a 0-1 share shown as a percentage, 'días' days; any other
 * unit is appended as written by the engine.
 */
export function formatUnitValue(value: number | string | boolean | null, unit = ''): string {
	if (value === null || value === '') return '—';
	if (typeof value === 'boolean') return value ? 'Sí' : 'No';
	if (typeof value === 'string') return unit ? `${value}${NBSP}${unit}` : value;
	if (unit === 'EUR') return formatMoney(value);
	if (unit === 'cuota') return formatPercent(value, Number.isInteger(value * 100) ? 0 : 1);
	if (unit === 'días') return formatDays(value);
	return unit ? `${formatQuantity(value)}${NBSP}${unit}` : formatQuantity(value);
}

/** Evidence period: 'YYYY-MM', 'YYYY-MM-DD' or a 'from..to' range of either. */
export function formatEvidencePeriod(period: string): string {
	const one = (part: string) => {
		const [year, month, day] = part.split('-').map(Number);
		return new Intl.DateTimeFormat('es-ES', {
			year: 'numeric',
			month: 'short',
			...(day ? { day: 'numeric' } : {})
		}).format(new Date(year, month - 1, day || 1));
	};
	return period.split('..').map(one).join(' – ');
}
