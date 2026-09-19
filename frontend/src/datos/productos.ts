// El catálogo de los 7 productos financieros (Linear QUA-7 y docs/PRODUCT_ICONOGRAPHY.md del
// equipo). Esto es la definición del producto, no un dato de ninguna empresa: qué tiene cada una
// sale de products/<id>.json y qué le encaja, de las acciones del motor (ver encaje.ts).

import type { ProductoId } from './contrato';
export type { ProductoId } from './contrato';

export type Familia = 'proteccion' | 'cobertura' | 'inversion';

export const FAMILIAS: Record<Familia, { nombre: string; lema: string; tono: string }> = {
	proteccion: { nombre: 'Protección', lema: 'Escudo, colchón y flujo garantizado', tono: 'azules' },
	cobertura: { nombre: 'Cobertura', lema: 'Mitigar la concentración de riesgo', tono: 'violeta' },
	inversion: { nombre: 'Inversión', lema: 'Excedente que rinde, crecimiento ordenado', tono: 'verdes y dorados' },
};

export interface Producto {
	id: ProductoId;
	nombre: string;
	/** Con artículo, para frases: «el factoring», «una línea de crédito». */
	articulo: string;
	familia: Familia;
	/** Solo en inversión: progresión de 1 (liquidez) a 3 (muy largo plazo). */
	nivel?: 1 | 2 | 3;
	metafora: string;
	color: string;
	tinte: string;
	prioridad: 'Alta' | 'Media' | 'Baja';
}

export const PRODUCTOS: Producto[] = [
	{ id: 'linea_credito', nombre: 'Línea de crédito', articulo: 'una línea de crédito', familia: 'proteccion', metafora: 'Red de seguridad ante tensión de liquidez', color: '#3d4fc4', tinte: '#eef0fc', prioridad: 'Alta' },
	{ id: 'factoring', nombre: 'Factoring', articulo: 'el factoring', familia: 'proteccion', metafora: 'Convertir facturas pendientes en caja hoy', color: '#2690cc', tinte: '#e7f4fb', prioridad: 'Alta' },
	{ id: 'confirming', nombre: 'Confirming', articulo: 'el confirming', familia: 'proteccion', metafora: 'Orden y garantía en los pagos a proveedores', color: '#4a6584', tinte: '#edf1f6', prioridad: 'Media' },
	{ id: 'seguro_credito', nombre: 'Seguro de crédito', articulo: 'un seguro de crédito', familia: 'cobertura', metafora: 'Cubrir el riesgo de un gran cliente', color: '#8a4fd8', tinte: '#f4eefc', prioridad: 'Media' },
	{ id: 'cuenta_remunerada', nombre: 'Cuenta remunerada', articulo: 'una cuenta remunerada', familia: 'inversion', nivel: 1, metafora: 'El dinero depositado empieza a rendir', color: '#1a9d76', tinte: '#e6f6f0', prioridad: 'Baja' },
	{ id: 'depositos', nombre: 'Depósitos y letras', articulo: 'un depósito o letras', familia: 'inversion', nivel: 2, metafora: 'Bloquear capital con vencimiento', color: '#8a8423', tinte: '#f5f3e1', prioridad: 'Baja' },
	{ id: 'plan_pensiones', nombre: 'Plan de pensiones', articulo: 'un plan de pensiones', familia: 'inversion', nivel: 3, metafora: 'Composición a muy largo plazo', color: '#b3841a', tinte: '#fbf3e0', prioridad: 'Baja' },
];
export const producto = (id: ProductoId) => PRODUCTOS.find((p) => p.id === id)!;
