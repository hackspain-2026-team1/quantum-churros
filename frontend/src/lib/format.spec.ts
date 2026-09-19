import { describe, expect, it } from 'vitest';
import {
	formatEvidencePeriod,
	formatScore,
	formatScoreDelta,
	formatUnitValue,
	shortHash
} from './format';

const NBSP = '\u00A0';

describe('es-ES formatters for bundle values', () => {
	it('renders integer tenths as score points with one decimal', () => {
		expect(formatScore(724)).toBe('72,4');
		expect(formatScore(500)).toBe('50,0');
		expect(formatScoreDelta(-61)).toBe('-6,1');
		expect(formatScoreDelta(12)).toBe('+1,2');
		expect(formatScoreDelta(0)).toBe('0,0');
	});

	it('formats a value according to its unit', () => {
		expect(formatUnitValue(83281.13, 'EUR')).toBe(`83.281,13${NBSP}€`);
		expect(formatUnitValue(0.41, 'cuota')).toBe(`41${NBSP}%`);
		expect(formatUnitValue(16, 'días')).toBe(`16${NBSP}días`);
		expect(formatUnitValue(3, 'grupos')).toBe(`3${NBSP}grupos`);
		expect(formatUnitValue(true)).toBe('Sí');
		expect(formatUnitValue(null, 'EUR')).toBe('—');
	});

	it('formats evidence periods and hashes', () => {
		expect(formatEvidencePeriod('2026-06..2026-08')).toBe('jun 2026 – ago 2026');
		expect(shortHash('sha256:0123456789abcdef')).toBe('0123456789');
		expect(shortHash('abc')).toBe('abc');
	});
});
