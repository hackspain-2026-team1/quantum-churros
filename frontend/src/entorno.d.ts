/// <reference types="vite/client" />

interface ImportMetaEnv {
	/** Raíz del bundle del motor. Por defecto, `${BASE_URL}datos/`. */
	readonly VITE_DATOS?: string;
	/** Raíz de los datos que genera Rumbo. Por defecto, `${BASE_URL}rumbo/`. */
	readonly VITE_RUMBO?: string;
}
