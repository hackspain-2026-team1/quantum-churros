export type CompanySignal = {
	id: string;
	name: string;
	score: number;
	delta: number;
	signal: string;
	confidence: string;
	intent: string;
};

export type ScoreDriver = {
	feature: string;
	label: string;
	direction: 'positive' | 'negative' | 'neutral';
	contribution: number;
	observed: number;
	baseline: number;
	evidence: string;
};

export type RecommendedAction = {
	id: string;
	priority: string;
	title: string;
	rationale: string;
	impact: string;
	owner: string;
	status: string;
	intent: string;
};

export type DemoOverview = {
	group: { id: string; name: string; period: string; score: number; delta: number };
	trajectory: number[];
	companies: CompanySignal[];
	snapshot: {
		entity_id: string;
		month: string;
		score: number;
		delta: number;
		trend: string;
		persistence_months: number;
		confidence: number;
		drivers: ScoreDriver[];
		detected_since: string | null;
		feature_version: string;
		model_version: string;
		dataset_hash: string;
	};
	actions: RecommendedAction[];
};

export type ScenarioResult = {
	scenario_id: string;
	status: string;
	base_score: number;
	projected_score: number;
	projected_cash: number;
	confidence_low: number;
	confidence_high: number;
};
