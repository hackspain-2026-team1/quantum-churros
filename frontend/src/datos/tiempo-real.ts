import { cabecerasFinanciacion, type IdentidadFinanciacion } from './financiacion';

export interface EventoFinanciacion {
	id: string;
	type: string;
	aggregate_id: string;
	created_at: string;
	payload: Record<string, unknown>;
}

export function conectarFinanciacion(identity: IdentidadFinanciacion, alEvento: (event: EventoFinanciacion) => void, alEstado: (state: 'conectado' | 'reintentando') => void): () => void {
	const controller = new AbortController();
	void escuchar();

	async function escuchar() {
		let retry = 800;
		while (!controller.signal.aborted) {
			try {
				const response = await fetch('/api/v1/financing/events', { headers: cabecerasFinanciacion(identity), signal: controller.signal });
				if (!response.ok || !response.body) throw new Error('stream unavailable');
				alEstado('conectado');
				retry = 800;
				const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
				let buffer = '';
				while (!controller.signal.aborted) {
					const { value, done } = await reader.read();
					if (done) break;
					buffer += value;
					const frames = buffer.split('\n\n');
					buffer = frames.pop() ?? '';
					for (const frame of frames) {
						const data = frame.split('\n').find((line) => line.startsWith('data: '));
						if (data) alEvento(JSON.parse(data.slice(6)) as EventoFinanciacion);
					}
				}
			} catch (error) {
				if (controller.signal.aborted) return;
				alEstado('reintentando');
				await new Promise((resolve) => setTimeout(resolve, retry));
				retry = Math.min(retry * 2, 8_000);
			}
		}
	}

	return () => controller.abort();
}
