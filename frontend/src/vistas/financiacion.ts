import { financiacionApi, type EspacioFinanciacion, type IdentidadFinanciacion, type IdentidadesDemo, type RolFinanciacion } from '../datos/financiacion';
import { conectarFinanciacion, type EventoFinanciacion } from '../datos/tiempo-real';
import type { Almacen, Estado } from '../estado';
import { vistaCaso } from './casos';
import { h, vaciar } from './dom';
import { vistaOfertas } from './ofertas';
import { vistaProveedor } from './proveedor';

const ROLES: { id: RolFinanciacion; label: string; detail: string }[] = [
	{ id: 'consultant', label: 'Consultor', detail: 'Detecta y prepara el caso' },
	{ id: 'company', label: 'Empresa', detail: 'Autoriza y decide' },
	{ id: 'provider', label: 'Proveedor', detail: 'Evalúa y oferta' },
];

export function crearFinanciacion(S: Almacen, alActualizar: () => void) {
	const raiz = h('article', { class: 'financiacion' });
	let demo: IdentidadesDemo | null = null;
	let espacio: EspacioFinanciacion | null = null;
	let cargando = false;
	let error = '';
	let proveedorActivo = 'provider';
	let eventos: EventoFinanciacion[] = [];
	let desconectar: (() => void) | null = null;
	let claveConexion = '';

	async function pintar(e: Estado) {
		pintarBase(e);
		if (!cargando && (!demo || !espacio || espacio.role !== e.finRol)) await cargar(e);
	}

	async function cargar(e: Estado) {
		cargando = true;
		error = '';
		pintarBase(e);
		try {
			demo ??= await financiacionApi.identidades();
			const identity = identidad(e.finRol);
			espacio = await financiacionApi.espacio(identity);
			conectar(identity);
		} catch (reason) {
			error = reason instanceof Error ? reason.message : String(reason);
		} finally {
			cargando = false;
			pintarBase(S.e);
			alActualizar();
		}
	}

	function identidad(rol: RolFinanciacion): IdentidadFinanciacion {
		if (!demo) throw new Error('El perfil demo no está disponible');
		const key = rol === 'provider' ? proveedorActivo : rol;
		const identity = demo.identities[key];
		if (!identity) throw new Error(`Falta la identidad ${key}`);
		return identity;
	}

	function conectar(identity: IdentidadFinanciacion) {
		const key = `${identity.organization_id}:${identity.role}`;
		if (key === claveConexion) return;
		desconectar?.();
		claveConexion = key;
		desconectar = conectarFinanciacion(identity, (event) => {
			eventos = [event, ...eventos.filter((item) => item.id !== event.id)].slice(0, 8);
			void cargar(S.e);
		}, (state) => raiz.dataset.stream = state);
	}

	function pintarBase(e: Estado) {
		vaciar(raiz);
		// El CFO es siempre la empresa: ni elige rol ni ve la mesa del banco.
		const soloEmpresa = e.modo === 'cfo';
		const navegacion = h('nav', { class: 'fin-roles', 'aria-label': 'Espacio de trabajo' });
		if (!soloEmpresa) for (const role of ROLES) navegacion.append(h('button', { type: 'button', 'aria-current': e.finRol === role.id ? 'page' : undefined, onclick: () => S.fijar({ finRol: role.id, finCaso: null }, true) }, h('strong', {}, role.label), h('span', {}, role.detail)));
		raiz.append(h('header', { class: 'fin-cabecera' }, h('div', {}, h('span', { class: 'fin-modo' }, soloEmpresa ? 'Tu financiación' : 'Espacio de financiación'), h('h1', {}, soloEmpresa ? 'De una señal a una decisión tuya' : 'De una señal a una decisión'), h('p', {}, soloEmpresa ? 'El score anticipa la necesidad. Tú autorizas, comparas y decides.' : 'El score anticipa la necesidad. Las personas autorizan, comparan y deciden.')), h('div', { class: 'fin-directo', role: 'status' }, h('span', {}, ''), raiz.dataset.stream === 'conectado' ? 'En directo' : 'Conectando')), navegacion);
		if (error) raiz.append(h('div', { class: 'fin-error', role: 'alert' }, h('strong', {}, 'No se puede abrir financiación'), h('span', {}, error), error.includes('disabled') ? h('span', {}, 'Activa FINANCING_DEMO_ENABLED en el servicio API.') : null));
		if (cargando) {
			raiz.append(h('div', { class: 'fin-esqueleto', 'aria-label': 'Cargando el espacio de financiación' }, h('span'), h('span'), h('span')));
			return;
		}
		if (!demo || !espacio) return;
		if (e.finRol !== 'provider' && !espacio.cases.length && !espacio.opportunities.length) {
			raiz.append(h('section', { class: 'fin-inicio' },
				h('div', {}, h('h2', {}, soloEmpresa ? 'No tienes ninguna solicitud abierta' : 'El escenario todavía no ha comenzado'),
					h('p', {}, soloEmpresa ? 'Cuando el score anticipa una necesidad, Rumbo prepara el caso y tú decides si se abre la ronda.' : 'FIN-024 genera una señal persistida y abre un caso en revisión. Cada ejecución conserva la anterior para mantener la auditoría.')),
				h('button', { type: 'button', class: 'fin-boton primario', onclick: () => ejecutar(async () => { const started = await financiacionApi.iniciar(); demo = { scenario: 'FIN-024', identities: started.identities }; S.fijar({ finCaso: started.case_id }, false); }) }, soloEmpresa ? 'Abrir una solicitud' : 'Iniciar escenario FIN-024')));
			return;
		}
		if (e.finRol === 'provider' && !soloEmpresa) {
			pintarProveedor(e);
		} else {
			pintarExpediente(e);
		}
		pintarActividad();
	}

	function pintarExpediente(e: Estado) {
		const expediente = espacio!.cases.find((item) => item.case.id === e.finCaso) ?? espacio!.cases[0];
		if (!expediente) return;
		if (e.finCaso !== expediente.case.id) queueMicrotask(() => S.fijar({ finCaso: expediente.case.id }, false));
		const identity = identidad(e.finRol);
		const contenido = h('div', { class: 'fin-contenido' });
		contenido.append(vistaCaso(expediente, e.finRol, {
			autorizar: (scope) => void ejecutar(() => financiacionApi.autorizar(identity, expediente.case, scope)),
			publicar: () => void ejecutar(() => financiacionApi.publicar(identity, expediente.case)),
			revocar: () => void ejecutar(() => financiacionApi.revocar(identity, expediente.case)),
		}));
		if (['published', 'shortlisted', 'accepted'].includes(expediente.case.status)) contenido.append(vistaOfertas(expediente, e.finRol, {
			preseleccionar: (providerOrgId) => void ejecutar(() => financiacionApi.preseleccionar(identity, expediente.case, providerOrgId)),
			aceptar: (offerId) => void ejecutar(() => financiacionApi.aceptar(identity, expediente.case, offerId)),
		}));
		raiz.append(contenido);
	}

	function pintarProveedor(e: Estado) {
		const proveedores = [
			{ key: 'provider', label: 'Norte Capital', identity: demo!.identities.provider },
			{ key: 'provider_alt', label: 'Banco Atlas', identity: demo!.identities.provider_alt },
		];
		raiz.append(h('div', { class: 'fin-contenido' }, vistaProveedor(espacio!.cases, espacio!.opportunities, proveedores, proveedorActivo, (key) => {
			proveedorActivo = key;
			espacio = null;
			void cargar(e);
		}, (identity, opportunityId, values) => void ejecutar(() => financiacionApi.oferta(identity, opportunityId, values)))));
	}

	function pintarActividad() {
		const mensajes: Record<string, string> = { 'funding_need.detected': 'Necesidad anticipada', 'case.created': 'Caso abierto por el consultor', 'case.authorized': 'Empresa autorizó la ronda', 'opportunity.published': 'Teaser publicado', 'offer.submitted': 'Proveedor presentó condiciones', 'case.shortlisted': 'Proveedor preseleccionado', 'offer.accepted': 'Oferta aceptada', 'access.revoked': 'Acceso revocado' };
		const lista = h('ol', { class: 'fin-eventos' });
		for (const event of eventos) lista.append(h('li', {}, h('time', {}, new Intl.DateTimeFormat('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(event.created_at))), h('span', {}, mensajes[event.type] ?? event.type)));
		if (!eventos.length) lista.append(h('li', { class: 'vacio' }, h('span', {}, 'Las decisiones nuevas aparecerán aquí sin recargar.')));
		raiz.append(h('aside', { class: 'fin-actividad', 'aria-label': 'Actividad en vivo' }, h('div', {}, h('strong', {}, 'Actividad en vivo'), h('span', {}, 'Outbox · SSE')), lista));
	}

	async function ejecutar(task: () => Promise<unknown>) {
		cargando = true;
		error = '';
		pintarBase(S.e);
		try {
			await task();
			espacio = await financiacionApi.espacio(identidad(S.e.finRol));
		} catch (reason) {
			error = reason instanceof Error ? reason.message : String(reason);
		} finally {
			cargando = false;
			pintarBase(S.e);
			alActualizar();
		}
	}

	return { raiz, pintar: (e: Estado) => { void pintar(e); }, desconectar: () => desconectar?.() };
}
