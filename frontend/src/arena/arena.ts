// El motor de arena. Un solo lienzo WebGL2 con N granos que componen todas las figuras de la
// interfaz. Cada grano tiene un destino; al cambiar de escena se disuelve (turbulencia) y vuelve a
// posarse con un muelle amortiguado. El cursor aparta la arena como una mano.
// La simulación va en CPU sobre arrays tipados (≈1 ms para 32.000 granos); la GPU solo pinta.

export const PALETA: [number, number, number][] = [
	[5, 11, 44], // 0 tinta (#050b2c)
	[194, 64, 31], // 1 peligro (#c2401f)
	[8, 171, 57], // 2 éxito (#08ab39)
	[56, 120, 246], // 3 información y selección (#3878f6)
	[223, 182, 49], // 4 aviso (#dfb631)
	[157, 75, 221], // 5 TellMe (#9d4bdd)
	[110, 112, 124], // 6 apagado (#6e707c)
	[190, 192, 204], // 7 filete (#bec0cc)
];
export const TONO = { tinta: 0, peligro: 1, exito: 2, info: 3, aviso: 4, tellme: 5, apagado: 6, filete: 7 } as const;

export interface Escena {
	x: Float32Array;
	y: Float32Array;
	tono: Uint8Array;
	alfa: Float32Array;
	talla: Float32Array;
	/** Segundos que espera cada grano antes de partir (permite barridos y ondas). */
	espera: Float32Array;
	/** Turbulencia al partir: 0 = deslizarse, 1 = disolverse del todo. */
	turbulencia: number;
	/** Rigidez del muelle (ω en rad/s). */
	rigidez?: number;
}

export function escenaVacia(n: number): Escena {
	return {
		x: new Float32Array(n), y: new Float32Array(n), tono: new Uint8Array(n),
		alfa: new Float32Array(n), talla: new Float32Array(n).fill(1.8), espera: new Float32Array(n),
		turbulencia: 0.6,
	};
}

const VS = `#version 300 es
in vec3 a_pt;
in vec4 a_col;
in float a_fase;
uniform vec2 u_res;
uniform float u_dpr;
uniform float u_t;
uniform float u_respira;
uniform float u_desp;
uniform vec2 u_corte;
out vec4 v_col;
void main() {
	float f = a_fase * 6.2831;
	vec2 p = a_pt.xy + vec2(sin(u_t * 0.83 + f), cos(u_t * 0.61 + f * 1.7)) * u_respira;
	p.y -= u_desp;
	vec2 c = p / u_res * 2.0 - 1.0;
	gl_Position = vec4(c.x, -c.y, 0.0, 1.0);
	gl_PointSize = a_pt.z * u_dpr;
	// Fuera de la ventana visible (una página que se desplaza), el grano no se pinta.
	v_col = (p.y < u_corte.x || p.y > u_corte.y) ? vec4(0.0) : a_col;
}`;

const FS = `#version 300 es
precision mediump float;
in vec4 v_col;
out vec4 o;
void main() {
	float r = length(gl_PointCoord - 0.5);
	float a = v_col.a * smoothstep(0.5, 0.3, r);
	o = vec4(v_col.rgb * a, a);
}`;

export class Arena {
	readonly n: number;
	readonly px: Float32Array; readonly py: Float32Array;
	private vx: Float32Array; private vy: Float32Array;
	private tx: Float32Array; private ty: Float32Array;
	private sx: Float32Array; private sy: Float32Array; // destino pendiente
	private espera: Float32Array;
	private agit: Float32Array;
	private turbPend: Float32Array;
	private alfa: Float32Array; private alfaObj: Float32Array; private alfaPend: Float32Array;
	private talla: Float32Array; private tallaObj: Float32Array; private tallaPend: Float32Array;
	private tono: Uint8Array; private tonoPend: Uint8Array;
	private rig: Float32Array;
	private fase: Float32Array;
	private omega = 7.5;

	private gl: WebGL2RenderingContext;
	private prog: WebGLProgram;
	private bufPt: WebGLBuffer; private bufCol: WebGLBuffer;
	private datosPt: Float32Array; private datosCol: Uint8Array;
	private u: Record<string, WebGLUniformLocation | null> = {};

	private ancho = 0; private alto = 0; private dpr = 0;
	private t0 = performance.now();
	private ultimo = performance.now();
	private raf = 0;
	private puntero = { x: -1e4, y: -1e4, activo: false, fuerza: 0 };
	private quieto = false;
	/** Desplazamiento vertical de la página (los destinos van en coordenadas de página). */
	private desp = 0;
	/** Franja visible en pantalla [arriba, abajo]; fuera de ella la arena no se pinta. */
	private corte: [number, number] = [-1e6, 1e6];
	reducido = matchMedia('(prefers-reduced-motion: reduce)').matches;
	respira = 0.35;
	/** Coste medio por fotograma en ms (media exponencial): simulación y pintado. */
	coste = { sim: 0, pinta: 0 };

	constructor(private lienzo: HTMLCanvasElement, n: number) {
		this.n = n;
		const F = () => new Float32Array(n);
		this.px = F(); this.py = F(); this.vx = F(); this.vy = F();
		this.tx = F(); this.ty = F(); this.sx = F(); this.sy = F();
		this.espera = F(); this.agit = F(); this.turbPend = F();
		this.alfa = F(); this.alfaObj = F(); this.alfaPend = F();
		this.talla = F().fill(1.6); this.tallaObj = F().fill(1.6); this.tallaPend = F().fill(1.6);
		this.tono = new Uint8Array(n); this.tonoPend = new Uint8Array(n);
		this.rig = F(); this.fase = F();
		for (let i = 0; i < n; i++) { this.rig[i] = 0.72 + Math.random() * 0.56; this.fase[i] = Math.random(); }

		const gl = lienzo.getContext('webgl2', { antialias: false, premultipliedAlpha: true, alpha: true });
		if (!gl) throw new Error('WebGL2 no disponible');
		this.gl = gl;
		this.prog = this.programa(VS, FS);
		for (const nombre of ['u_res', 'u_dpr', 'u_t', 'u_respira', 'u_desp', 'u_corte']) this.u[nombre] = gl.getUniformLocation(this.prog, nombre);

		this.datosPt = new Float32Array(n * 3);
		this.datosCol = new Uint8Array(n * 4);
		const vao = gl.createVertexArray();
		gl.bindVertexArray(vao);
		this.bufPt = this.atributo('a_pt', this.datosPt, 3, gl.FLOAT, false);
		this.bufCol = this.atributo('a_col', this.datosCol, 4, gl.UNSIGNED_BYTE, true);
		this.atributo('a_fase', this.fase, 1, gl.FLOAT, false, gl.STATIC_DRAW);
		gl.enable(gl.BLEND);
		gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);

		this.redimensionar();
		// Los granos nacen dispersos por todo el lienzo: la primera escena los recoge.
		for (let i = 0; i < n; i++) {
			this.px[i] = this.tx[i] = this.sx[i] = Math.random() * this.ancho;
			this.py[i] = this.ty[i] = this.sy[i] = this.alto * (0.35 + Math.random() * 0.65);
		}
		addEventListener('pointermove', (e) => this.moverPuntero(e));
		addEventListener('pointerdown', () => (this.puntero.fuerza = 1.8));
		document.addEventListener('pointerleave', () => (this.puntero.activo = false));
		this.bucle = this.bucle.bind(this);
		this.raf = requestAnimationFrame(this.bucle);
	}

	get dimensiones() { return { ancho: this.ancho, alto: this.alto }; }

	/** La página se ha desplazado: la arena la sigue al instante, sin simular nada. */
	desplazar(dy: number) {
		if (dy === this.desp) return;
		this.desp = dy;
		this.despertar();
		if (this.quieto || this.reducido) this.pintar((performance.now() - this.t0) / 1000);
	}

	/** Limita la arena a una franja de la pantalla (la zona de la página que se desplaza). */
	recortar(arriba: number, abajo: number) {
		this.corte = [arriba, abajo];
		this.despertar();
	}

	/** Pinta una vez aunque el bucle duerma (tras desplazar con la arena quieta). */
	repintar() { this.pintar((performance.now() - this.t0) / 1000); }

	redimensionar() {
		const dpr = Math.min(devicePixelRatio || 1, 2);
		const ancho = this.lienzo.clientWidth, alto = this.lienzo.clientHeight;
		// Cambiar el tamaño del lienzo lo borra: solo se hace si cambia de verdad, y luego se repinta.
		if (ancho === this.ancho && alto === this.alto && dpr === this.dpr) return;
		this.dpr = dpr;
		this.ancho = ancho;
		this.alto = alto;
		this.lienzo.width = Math.round(ancho * dpr);
		this.lienzo.height = Math.round(alto * dpr);
		this.gl.viewport(0, 0, this.lienzo.width, this.lienzo.height);
		if (this.raf !== undefined) this.despertar();
	}

	/** Cambia de escena. Cada grano parte hacia su nuevo destino tras su espera. */
	fijar(e: Escena) {
		this.omega = e.rigidez ?? 7.5;
		const turb = this.reducido ? 0 : e.turbulencia;
		for (let i = 0; i < this.n; i++) {
			this.sx[i] = e.x[i]; this.sy[i] = e.y[i];
			this.alfaPend[i] = e.alfa[i];
			this.tallaPend[i] = e.talla[i];
			this.tonoPend[i] = e.tono[i];
			this.turbPend[i] = turb;
			this.espera[i] = this.reducido ? 0 : e.espera[i];
			if (this.espera[i] <= 0) this.partir(i);
		}
		if (this.reducido) {
			for (let i = 0; i < this.n; i++) { this.px[i] = e.x[i]; this.py[i] = e.y[i]; this.alfa[i] = this.alfaObj[i]; this.talla[i] = this.tallaObj[i]; }
			this.pintar((performance.now() - this.t0) / 1000);
		}
		this.despertar();
	}

	/** Mueve destinos sin disolver (el reloj: los grupos se deslizan de un mes a otro). */
	deslizar(e: Escena) {
		this.fijar({ ...e, turbulencia: Math.min(e.turbulencia, 0.08) });
	}

	/** Un temblor local: los granos alrededor de (x, y) se agitan y vuelven. */
	pulsar(x: number, y: number, radio = 60, fuerza = 0.5) {
		const r2 = radio * radio;
		for (let i = 0; i < this.n; i++) {
			const dx = this.px[i] - x, dy = this.py[i] - y;
			if (dx * dx + dy * dy < r2) this.agit[i] = Math.max(this.agit[i], fuerza);
		}
		this.despertar();
	}

	private partir(i: number) {
		this.tx[i] = this.sx[i]; this.ty[i] = this.sy[i];
		this.alfaObj[i] = this.alfaPend[i];
		this.tallaObj[i] = this.tallaPend[i];
		this.tono[i] = this.tonoPend[i];
		this.agit[i] = Math.max(this.agit[i], this.turbPend[i]);
		this.espera[i] = 0;
	}

	private moverPuntero(e: PointerEvent) {
		const r = this.lienzo.getBoundingClientRect();
		this.puntero.x = e.clientX - r.left;
		this.puntero.y = e.clientY - r.top + this.desp;
		this.puntero.activo = true;
		this.despertar();
	}

	private despertar() {
		if (this.quieto) { this.quieto = false; this.ultimo = performance.now(); this.raf = requestAnimationFrame(this.bucle); }
	}

	private bucle(ahora: number) {
		const dt = Math.min(0.033, (ahora - this.ultimo) / 1000);
		this.ultimo = ahora;
		const t = (ahora - this.t0) / 1000;
		const t0 = performance.now();
		const energia = this.simular(dt, t);
		const t1 = performance.now();
		this.pintar(t);
		const t2 = performance.now();
		this.coste.sim = this.coste.sim * 0.95 + (t1 - t0) * 0.05;
		this.coste.pinta = this.coste.pinta * 0.95 + (t2 - t1) * 0.05;
		this.puntero.fuerza *= Math.exp(-dt * 5);
		// Con la arena en reposo y sin respiración, el bucle se duerme para no gastar batería.
		if (energia < 0.02 && (this.reducido || this.respira === 0) && !this.puntero.activo) { this.quieto = true; return; }
		this.raf = requestAnimationFrame(this.bucle);
	}

	private simular(dt: number, t: number) {
		const { px, py, vx, vy, tx, ty, agit, espera, rig } = this;
		const w = this.omega;
		const P = this.puntero;
		const R = 70, R2 = R * R;
		const fuerzaP = P.activo && !this.reducido ? 2600 * (1 + P.fuerza) : 0;
		let energia = 0;
		const decae = Math.exp(-dt * 2.4);
		const k = Math.min(1, dt * 7);
		for (let i = 0; i < this.n; i++) {
			if (espera[i] > 0) { espera[i] -= dt; if (espera[i] <= 0) this.partir(i); }
			const wi = w * rig[i];
			const K = wi * wi, C = 1.55 * wi;
			let ax = K * (tx[i] - px[i]) - C * vx[i];
			let ay = K * (ty[i] - py[i]) - C * vy[i];
			const a = agit[i];
			if (a > 0.002) {
				const ang = this.fase[i] * 40 + t * 2.1 + px[i] * 0.012 + py[i] * 0.009;
				ax += Math.cos(ang) * a * 1900;
				ay += Math.sin(ang * 1.31) * a * 1900 - a * 300;
				agit[i] = a * decae;
			}
			if (fuerzaP) {
				const dx = px[i] - P.x, dy = py[i] - P.y;
				const d2 = dx * dx + dy * dy;
				if (d2 < R2 && d2 > 0.01) {
					const d = Math.sqrt(d2);
					const f = (1 - d / R) * (1 - d / R) * fuerzaP;
					ax += (dx / d) * f; ay += (dy / d) * f;
				}
			}
			vx[i] += ax * dt; vy[i] += ay * dt;
			px[i] += vx[i] * dt; py[i] += vy[i] * dt;
			energia += Math.abs(vx[i]) + Math.abs(vy[i]);
			this.alfa[i] += (this.alfaObj[i] - this.alfa[i]) * k;
			this.talla[i] += (this.tallaObj[i] - this.talla[i]) * k;
		}
		return energia / this.n;
	}

	private pintar(t: number) {
		const gl = this.gl;
		const P = this.datosPt, Cc = this.datosCol;
		for (let i = 0; i < this.n; i++) {
			P[i * 3] = this.px[i]; P[i * 3 + 1] = this.py[i]; P[i * 3 + 2] = this.talla[i];
			const c = PALETA[this.tono[i]];
			Cc[i * 4] = c[0]; Cc[i * 4 + 1] = c[1]; Cc[i * 4 + 2] = c[2];
			Cc[i * 4 + 3] = Math.max(0, Math.min(255, this.alfa[i] * 255));
		}
		gl.bindBuffer(gl.ARRAY_BUFFER, this.bufPt);
		gl.bufferSubData(gl.ARRAY_BUFFER, 0, P);
		gl.bindBuffer(gl.ARRAY_BUFFER, this.bufCol);
		gl.bufferSubData(gl.ARRAY_BUFFER, 0, Cc);
		gl.clearColor(0, 0, 0, 0);
		gl.clear(gl.COLOR_BUFFER_BIT);
		gl.useProgram(this.prog);
		gl.uniform2f(this.u.u_res, this.ancho, this.alto);
		gl.uniform1f(this.u.u_dpr, this.dpr);
		gl.uniform1f(this.u.u_t, t);
		gl.uniform1f(this.u.u_respira, this.reducido ? 0 : this.respira);
		gl.uniform1f(this.u.u_desp, this.desp);
		gl.uniform2f(this.u.u_corte, this.corte[0], this.corte[1]);
		gl.drawArrays(gl.POINTS, 0, this.n);
	}

	private programa(vs: string, fs: string) {
		const gl = this.gl;
		const sombra = (tipo: number, src: string) => {
			const s = gl.createShader(tipo)!;
			gl.shaderSource(s, src);
			gl.compileShader(s);
			if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? 'shader');
			return s;
		};
		const p = gl.createProgram()!;
		gl.attachShader(p, sombra(gl.VERTEX_SHADER, vs));
		gl.attachShader(p, sombra(gl.FRAGMENT_SHADER, fs));
		gl.linkProgram(p);
		if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) ?? 'programa');
		return p;
	}

	private atributo(nombre: string, datos: ArrayBufferView, tam: number, tipo: number, normalizado: boolean, uso: number = this.gl.DYNAMIC_DRAW) {
		const gl = this.gl;
		const buf = gl.createBuffer()!;
		gl.bindBuffer(gl.ARRAY_BUFFER, buf);
		gl.bufferData(gl.ARRAY_BUFFER, datos, uso);
		const loc = gl.getAttribLocation(this.prog, nombre);
		gl.enableVertexAttribArray(loc);
		gl.vertexAttribPointer(loc, tam, tipo, normalizado, 0, 0);
		return buf;
	}

	destruir() { cancelAnimationFrame(this.raf); }
}
