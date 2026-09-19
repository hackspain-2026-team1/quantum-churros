/// <reference types="vite/client" />

interface ImportMetaEnv {
	/** Raíz del bundle del motor. Por defecto, `${BASE_URL}datos/`. */
	readonly VITE_DATOS?: string;
	/** Raíz de los datos que genera Rumbo. Por defecto, `${BASE_URL}rumbo/`. */
	readonly VITE_RUMBO?: string;
	/** Worker rumbo-vista (Jev). Vacío: el monitor entiende solo por palabras clave. */
	readonly VITE_VISTA_URL?: string;
}
