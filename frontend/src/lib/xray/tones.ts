// One tone vocabulary for every screen, mapped onto the tokens of layout.css.

import type { AlertState, Band, CheckStatus, ConfLabel, Direction } from './contract.js';

export type Tone = 'danger' | 'warning' | 'signal' | 'success' | 'neutral';

export const BAND_TONE: Record<Band, Tone> = {
	critical: 'danger',
	watch: 'warning',
	stable: 'signal',
	solid: 'success'
};

export const DIRECTION_TONE: Record<Direction, Tone> = {
	improving: 'success',
	stable: 'neutral',
	deteriorating: 'danger',
	perimeter_shift: 'signal'
};

export const CONF_TONE: Record<ConfLabel, Tone> = {
	high: 'signal',
	medium: 'neutral',
	low: 'warning'
};

export const ALERT_STATE_TONE: Record<AlertState, Tone> = {
	fired: 'danger',
	suppressed: 'neutral',
	abstained: 'warning'
};

export const CHECK_STATUS_TONE: Record<CheckStatus, Tone> = {
	pass: 'success',
	fail: 'danger',
	info: 'signal',
	not_run: 'neutral'
};

/** Soft badge surface: border, background and text with AA contrast. */
export const TONE_BADGE: Record<Tone, string> = {
	danger: 'border-[var(--danger)]/30 bg-[var(--danger-soft)] text-[var(--danger-strong)]',
	warning: 'border-[var(--warning)]/40 bg-[var(--warning-soft)] text-[var(--warning-strong)]',
	signal: 'border-[var(--signal)]/30 bg-[var(--signal-soft)] text-[var(--signal-strong)]',
	success: 'border-[var(--success)]/30 bg-[var(--success-soft)] text-[var(--success-strong)]',
	neutral: 'border-border bg-muted text-muted-foreground'
};

export const TONE_TEXT: Record<Tone, string> = {
	danger: 'text-[var(--danger-strong)]',
	warning: 'text-[var(--warning-strong)]',
	signal: 'text-[var(--signal-strong)]',
	success: 'text-[var(--success-strong)]',
	neutral: 'text-muted-foreground'
};

export const TONE_DOT: Record<Tone, string> = {
	danger: 'bg-[var(--danger)]',
	warning: 'bg-[var(--warning)]',
	signal: 'bg-[var(--signal)]',
	success: 'bg-[var(--success)]',
	neutral: 'bg-muted-foreground/50'
};

/** CSS colour for SVG marks and inline styles. */
export const TONE_COLOR: Record<Tone, string> = {
	danger: 'var(--danger)',
	warning: 'var(--warning)',
	signal: 'var(--signal)',
	success: 'var(--success)',
	neutral: 'var(--muted-foreground)'
};
