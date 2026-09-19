import type { EntidadesM } from './contrato';

let grupos: EntidadesM['groups'] = {};
let empresas: EntidadesM['companies'] = {};

const numeroTecnico = (id: string) => Number(id.split('_')[1]);

export function fijarNombres(indice: EntidadesM | null, bundleId: string): boolean {
	if (!indice || indice.bundle_id !== bundleId) {
		grupos = {};
		empresas = {};
		return false;
	}
	grupos = indice.groups;
	empresas = indice.companies;
	return true;
}

export const nombreGrupo = (id: string) => grupos[id]?.name ?? `Grupo ${numeroTecnico(id)}`;
export const nombreEmpresa = (id: string) => empresas[id]?.name ?? `Empresa ${numeroTecnico(id)}`;
export const nombreLegal = (id: string) => empresas[id]?.legal_name ?? nombreEmpresa(id);
export const buscarNombre = (id: string) => grupos[id]?.name ?? empresas[id]?.name ?? id;
