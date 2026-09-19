// Static export bundle, mirror of contracts/xray-export-v1.schema.json.
//
// Months are 'YYYY-MM'. Every score-point quantity is an integer number of
// tenths (see fromTenths). For every entity-month, in integers:
//   base + sum(pillars[].contrib) - penalty - cap.amount === shown
// Columnar arrays align index by index with the months of their own file;
// null means the entity was not observed that month. Unknown properties are
// dropped on parse, so the engine may add optional fields without breaking us.

import { z } from 'zod';

export const BUNDLE_SCHEMA = 'xray-export-v1';
export const PILLAR_KEYS = ['liquidity', 'payments', 'collections', 'activity', 'debt'] as const;
export const BAND_KEYS = ['critical', 'watch', 'stable', 'solid'] as const;
export const DIRECTIONS = ['improving', 'stable', 'deteriorating', 'perimeter_shift'] as const;
export const NATURES = ['structural', 'shock_pending', 'bump'] as const;
export const CONF_LABELS = ['high', 'medium', 'low'] as const;
export const ALERT_KINDS = [
	'deterioration_structural',
	'improvement_structural',
	'level_critical',
	'cap_fired',
	'stale_feed'
] as const;
export const ALERT_STATES = ['fired', 'suppressed', 'abstained'] as const;
export const CHECK_STATUSES = ['pass', 'fail', 'info', 'not_run'] as const;

// Paths relative to the bundle root (/data/v1/ in the deployed app).
export const BUNDLE_FILES = {
	manifest: 'manifest.json',
	portfolio: 'portfolio.json',
	alerts: 'alerts.json',
	receipt: 'receipt.json',
	group: (id: string) => `groups/${id}.json`,
	company: (id: string) => `companies/${id}.json`,
	evidence: (id: string) => `evidence/${id}.json`
} as const;

const schemaTag = z.literal(BUNDLE_SCHEMA);
const month = z.string().regex(/^[0-9]{4}-(0[1-9]|1[0-2])$/);
const entityId = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/);
const entityKind = z.enum(['group', 'company']);
const pillarKey = z.enum(PILLAR_KEYS);
const band = z.enum(BAND_KEYS);
const direction = z.enum(DIRECTIONS);
const nature = z.enum(NATURES);
const confLabel = z.enum(CONF_LABELS);
const tenths = z.number().int();
const scoreTenths = z.number().int().min(0).max(1000);
const count = z.number().int().min(0);
const share = z.number().min(0).max(1);
const code = z.string().regex(/^[a-z][a-z0-9_]{0,63}$/);
const text = z.string().min(1).max(400);
const nullableText = text.nullable();
const nullableLabel = z.string().min(1).max(80).nullable();
const codeTexts = z.record(text);

export const pillarSchema = z.object({
	key: pillarKey,
	score: scoreTenths.nullable(),
	w_eff: share,
	contrib: tenths,
	gates: z.array(code),
	note: nullableText
});

export const verdictSchema = z.object({
	available: z.boolean(),
	reason: code.nullable(),
	direction,
	nature: nature.nullable(),
	shock_pending: z.boolean(),
	shock_month: month.nullable(),
	delta3: tenths.nullable(),
	sigma: count.nullable(),
	delta3_sigma: z.number().nullable(),
	compared_to: month.nullable(),
	pillars_moved: z.array(pillarKey),
	persistence_months: count,
	detected_since: month.nullable()
});

// Optional, newer bundles only: what the entity could do next and what the score would become.
export const actionSchema = z.object({
	id: z.string().min(1).max(80),
	pillar: pillarKey.nullable().optional(),
	title: text,
	detail: z.string().max(600).nullable().optional(),
	current: z.number().nullable().optional(),
	target: z.number().nullable().optional(),
	unit: z.string().max(24).nullable().optional(),
	uplift_tenths: tenths,
	new_score_tenths: scoreTenths,
	effort: z.string().max(40).nullable().optional()
});
export const actionsCombinedSchema = z.object({ new_score: scoreTenths, uplift: tenths });

// The stage ladder: each stage acts on the month the previous one produced,
// up to the best score the bounded levers can reach.
export const planActionSchema = z.object({
	id: z.string().min(1).max(80),
	pillar: pillarKey.nullable().optional(),
	title: text,
	detail: z.string().max(600).nullable().optional(),
	current: z.number().nullable().optional(),
	target: z.number().nullable().optional(),
	unit: z.string().max(24).nullable().optional(),
	uplift_tenths: tenths,
	new_score_tenths: scoreTenths,
	effort: z.string().max(40).nullable().optional()
});
export const actionStageSchema = z.object({
	number: count,
	score_tenths: scoreTenths,
	uplift_tenths: tenths,
	actions: z.array(planActionSchema)
});
export const actionsPlanSchema = z.object({
	stages: z.array(actionStageSchema).min(1),
	max_score_tenths: scoreTenths,
	max_uplift_tenths: tenths
});

const entityMonthShape = z.object({
	month,
	shown: scoreTenths,
	band,
	level: scoreTenths,
	base: tenths,
	pillars: z.array(pillarSchema).length(PILLAR_KEYS.length),
	penalty: count,
	cap: z.object({ amount: count, rule: code.nullable(), fired: z.array(code) }),
	conf: z.object({
		value: share,
		label: confLabel,
		history: share,
		coverage: share,
		quality: share
	}),
	branch: z.string().regex(/^(none|[a-z]+(\+[a-z]+)*)$/),
	flags: z.array(code),
	feed_live: z.boolean(),
	months_observed: count,
	perimeter_changed: z.boolean(),
	verdict: verdictSchema,
	abstain: z.object({ reason: code, unlock: text }).nullable(),
	actions: z.array(actionSchema).optional(),
	actions_combined: actionsCombinedSchema.nullable().optional(),
	actions_plan: actionsPlanSchema.nullable().optional()
});

/** base + contributions - penalty - cap - shown, in tenths; 0 on a valid entity-month. */
export function identityGap(entry: z.infer<typeof entityMonthShape>): number {
	const contributions = entry.pillars.reduce((total, pillar) => total + pillar.contrib, 0);
	return entry.base + contributions - entry.penalty - entry.cap.amount - entry.shown;
}

export const entityMonthSchema = entityMonthShape.superRefine((entry, ctx) => {
	if (entry.pillars.some((pillar, index) => pillar.key !== PILLAR_KEYS[index])) {
		ctx.addIssue({ code: 'custom', message: 'pillars are not in contract order' });
	}
	const gap = identityGap(entry);
	if (gap !== 0) {
		ctx.addIssue({ code: 'custom', message: `waterfall misses shown by ${gap} tenths` });
	}
});

export const profileAttributeSchema = z.object({
	key: code,
	label: text,
	value: z.union([z.string().max(160), z.number(), z.boolean()]).nullable(),
	evidence: z.string().max(400),
	coverage: share
});

export const contextSchema = z.object({
	industry: z
		.object({
			slug: z.string().min(1).max(80),
			label: text,
			confidence: share,
			reason: z.string().max(400)
		})
		.nullable(),
	benchmark: z.object({ text, source: text }).nullable()
});

export const seriesSchema = z.object({
	key: code,
	label: text,
	unit: z.string().max(24),
	values: z.array(z.number().nullable())
});

export const suppressedBySchema = z.object({
	reason: code,
	since: month,
	until: month.nullable()
});

export const alertSchema = z
	.object({
		id: z.string().regex(/^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}:[0-9]{4}-(0[1-9]|1[0-2]):[a-z_]+$/),
		entity_kind: entityKind,
		entity_id: entityId,
		group_id: entityId,
		month,
		kind: z.enum(ALERT_KINDS),
		state: z.enum(ALERT_STATES),
		title: text,
		detail: text,
		shown: scoreTenths,
		suppressed_by: suppressedBySchema.nullable()
	})
	.refine((alert) => (alert.state === 'fired') === (alert.suppressed_by === null), {
		message: 'suppressed_by is set exactly when the alert is not fired'
	});

export const evidenceRowSchema = z.object({
	pillar: pillarKey.nullable(),
	label: z.string().min(1).max(120),
	value: z.union([z.number(), z.string().max(80)]).nullable(),
	unit: z.string().max(24),
	period: z.string().regex(/^[0-9]{4}-[0-9]{2}(-[0-9]{2})?(\.\.[0-9]{4}-[0-9]{2}(-[0-9]{2})?)?$/),
	source_file: z.string().regex(/^[A-Za-z0-9_./-]{1,64}$/),
	n_rows: count.nullable()
});

export const manifestSchema = z.object({
	schema: schemaTag,
	kind: z.literal('manifest'),
	bundle_id: z.string().regex(/^[0-9a-f]{64}$/),
	engine_version: z.string().min(1),
	params_hash: z.string().min(1),
	dataset_hash: z.string().min(1),
	generated_at: z
		.string()
		.regex(
			/^[0-9]{4}-[0-9]{2}-[0-9]{2}(T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]+)?)?(Z|[+-][0-9]{2}:[0-9]{2})?)?$/
		),
	months: z.array(month).min(1),
	counts: z.object({ groups: count, companies: count, alerts: count }),
	pillars: z
		.array(z.object({ key: pillarKey, label: text, weight: share, baseline: scoreTenths }))
		.length(PILLAR_KEYS.length),
	bands: z.array(z.object({ key: band, label: text, min: scoreTenths })).length(BAND_KEYS.length),
	glossary: z.object({
		gates: codeTexts,
		flags: codeTexts,
		caps: codeTexts,
		reasons: codeTexts
	})
});

const portfolioGroupSchema = z.object({
	id: entityId,
	n_companies: z.number().int().min(1),
	first_month: month,
	country: z.string().max(80).nullable(),
	size_band: z.string().max(80).nullable(),
	industry: z.string().max(120).nullable(),
	shown: z.array(scoreTenths.nullable()),
	band: z.array(band.nullable()),
	direction: z.array(direction.nullable()),
	nature: z.array(nature.nullable()),
	conf: z.array(confLabel.nullable()),
	abstained: z.array(z.boolean().nullable()),
	perimeter_changed: z.array(z.boolean().nullable()),
	alerts_fired: z.array(count),
	alerts_muted: z.array(count)
});

const PORTFOLIO_COLUMNS = [
	'shown',
	'band',
	'direction',
	'nature',
	'conf',
	'abstained',
	'perimeter_changed',
	'alerts_fired',
	'alerts_muted'
] as const;

export const portfolioSchema = z
	.object({
		schema: schemaTag,
		kind: z.literal('portfolio'),
		months: z.array(month).min(1),
		groups: z.array(portfolioGroupSchema)
	})
	.superRefine((portfolio, ctx) => {
		for (const group of portfolio.groups) {
			for (const column of PORTFOLIO_COLUMNS) {
				if (group[column].length !== portfolio.months.length) {
					ctx.addIssue({ code: 'custom', message: `${group.id}.${column} is not aligned` });
				}
			}
		}
	});

const groupCompanySchema = z.object({
	id: entityId,
	role: nullableLabel,
	treasury_class: nullableLabel,
	truth: nullableText,
	inherits_liquidity: z.boolean(),
	first_month: month,
	shown: z.array(scoreTenths.nullable()),
	band: z.array(band.nullable())
});

export const groupSchema = z
	.object({
		schema: schemaTag,
		kind: z.literal('group'),
		id: entityId,
		first_month: month,
		profile: z.array(profileAttributeSchema),
		context: contextSchema,
		months: z.array(entityMonthSchema).min(1),
		companies: z.array(groupCompanySchema),
		series: z.array(seriesSchema),
		alerts: z.array(alertSchema)
	})
	.superRefine((group, ctx) => {
		const size = group.months.length;
		for (const company of group.companies) {
			if (company.shown.length !== size || company.band.length !== size) {
				ctx.addIssue({ code: 'custom', message: `${company.id} is not aligned with months` });
			}
		}
		for (const series of group.series) {
			if (series.values.length !== size) {
				ctx.addIssue({ code: 'custom', message: `series ${series.key} is not aligned` });
			}
		}
	});

export const companySchema = z
	.object({
		schema: schemaTag,
		kind: z.literal('company'),
		id: entityId,
		group_id: entityId,
		role: nullableLabel,
		treasury_class: nullableLabel,
		truth: nullableText,
		inherits_liquidity: z.boolean(),
		first_month: month,
		profile: z.array(profileAttributeSchema),
		context: contextSchema,
		months: z.array(entityMonthSchema).min(1),
		series: z.array(seriesSchema),
		alerts: z.array(alertSchema)
	})
	.superRefine((company, ctx) => {
		for (const series of company.series) {
			if (series.values.length !== company.months.length) {
				ctx.addIssue({ code: 'custom', message: `series ${series.key} is not aligned` });
			}
		}
	});

export const evidenceSchema = z.object({
	schema: schemaTag,
	kind: z.literal('evidence'),
	entity_kind: entityKind,
	entity_id: entityId,
	group_id: entityId,
	months: z.array(z.object({ month, rows: z.array(evidenceRowSchema) }))
});

export const alertsSchema = z.object({
	schema: schemaTag,
	kind: z.literal('alerts'),
	alerts: z.array(alertSchema)
});

export const receiptCheckSchema = z.object({
	key: code,
	title: text,
	status: z.enum(CHECK_STATUSES),
	summary: text,
	metrics: z.array(
		z.object({
			label: text,
			value: z.union([z.number(), z.string().max(80), z.boolean()]).nullable(),
			unit: z.string().max(24)
		})
	),
	bars: z.array(z.object({ label: z.string().min(1).max(40), value: z.number() })).optional()
});

export const receiptSchema = z.object({
	schema: schemaTag,
	kind: z.literal('receipt'),
	engine_version: z.string().min(1),
	params_hash: z.string().min(1),
	dataset_hash: z.string().min(1),
	signals: z.array(z.object({ name: code, label: text, weight: share, why: text })),
	abstentions: z.array(
		z.object({
			entity_kind: entityKind,
			entity_id: entityId,
			group_id: entityId,
			month,
			reason: code,
			unlock: text
		})
	),
	checks: z.array(receiptCheckSchema)
});

export const bundleSchemas = {
	manifest: manifestSchema,
	portfolio: portfolioSchema,
	group: groupSchema,
	company: companySchema,
	evidence: evidenceSchema,
	alerts: alertsSchema,
	receipt: receiptSchema
} as const;

export type BundleKind = keyof typeof bundleSchemas;
export type BundleFile<K extends BundleKind> = z.infer<(typeof bundleSchemas)[K]>;

/** Throws a ZodError when the file breaks the contract. */
export function parseBundleFile<K extends BundleKind>(kind: K, data: unknown): BundleFile<K> {
	return bundleSchemas[kind].parse(data) as BundleFile<K>;
}

export type PillarKey = (typeof PILLAR_KEYS)[number];
export type Band = (typeof BAND_KEYS)[number];
export type Direction = (typeof DIRECTIONS)[number];
export type Nature = (typeof NATURES)[number];
export type ConfLabel = (typeof CONF_LABELS)[number];
export type AlertKind = (typeof ALERT_KINDS)[number];
export type AlertState = (typeof ALERT_STATES)[number];
export type CheckStatus = (typeof CHECK_STATUSES)[number];

export type Manifest = z.infer<typeof manifestSchema>;
export type Portfolio = z.infer<typeof portfolioSchema>;
export type PortfolioGroup = z.infer<typeof portfolioGroupSchema>;
export type GroupFile = z.infer<typeof groupSchema>;
export type GroupCompany = z.infer<typeof groupCompanySchema>;
export type CompanyFile = z.infer<typeof companySchema>;
export type EvidenceFile = z.infer<typeof evidenceSchema>;
export type EvidenceRow = z.infer<typeof evidenceRowSchema>;
export type AlertsFile = z.infer<typeof alertsSchema>;
export type Alert = z.infer<typeof alertSchema>;
export type SuppressedBy = z.infer<typeof suppressedBySchema>;
export type Receipt = z.infer<typeof receiptSchema>;
export type ReceiptCheck = z.infer<typeof receiptCheckSchema>;
export type EntityMonth = z.infer<typeof entityMonthSchema>;
export type EntityAction = z.infer<typeof actionSchema>;
export type ActionsCombined = z.infer<typeof actionsCombinedSchema>;
export type PillarEntry = z.infer<typeof pillarSchema>;
export type Verdict = z.infer<typeof verdictSchema>;
export type ProfileAttribute = z.infer<typeof profileAttributeSchema>;
export type EntityContext = z.infer<typeof contextSchema>;
export type Series = z.infer<typeof seriesSchema>;

/** Integer tenths -> score points. Format the result with one decimal. */
export function fromTenths(value: number): number {
	return value / 10;
}

// Closed vocabularies. Open codes (gates, flags, caps, reasons) come with
// their text in manifest.glossary; pillar and band labels in manifest too.
export const DIRECTION_TEXT: Record<Direction, string> = {
	improving: 'Mejora',
	stable: 'Estable',
	deteriorating: 'Deterioro',
	perimeter_shift: 'Cambio de perímetro'
};
export const NATURE_TEXT: Record<Nature, string> = {
	structural: 'Estructural',
	shock_pending: 'Shock por confirmar',
	bump: 'Bache'
};
export const CONF_TEXT: Record<ConfLabel, string> = {
	high: 'Alta',
	medium: 'Media',
	low: 'Baja'
};
export const ALERT_KIND_TEXT: Record<AlertKind, string> = {
	deterioration_structural: 'Deterioro estructural',
	improvement_structural: 'Mejora estructural',
	level_critical: 'Nivel crítico',
	cap_fired: 'Tope aplicado',
	stale_feed: 'Feed sin datos'
};
export const ALERT_STATE_TEXT: Record<AlertState, string> = {
	fired: 'Activa',
	suppressed: 'Suprimida',
	abstained: 'En abstención'
};
export const CHECK_STATUS_TEXT: Record<CheckStatus, string> = {
	pass: 'Superada',
	fail: 'No superada',
	info: 'Informativa',
	not_run: 'No ejecutada'
};
