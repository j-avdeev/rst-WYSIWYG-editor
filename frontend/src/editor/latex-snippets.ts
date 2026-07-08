// A curated, not-exhaustive LaTeX symbol palette (reference: latexeditor.lagrida.com),
// scoped to what shows up in engineering/physics rst docs: Greek letters,
// scripts, big operators, relations, brackets, common functions.

export interface Snippet {
  label: string
  // Wrap the current selection (or open a cursor slot) with before/after.
  before?: string
  after?: string
  // Or insert plain text at the cursor with no wrapping.
  insert?: string
  title?: string
}

export interface SnippetGroup {
  name: string
  items: Snippet[]
}

const greekLower = [
  ['α', 'alpha'], ['β', 'beta'], ['γ', 'gamma'], ['δ', 'delta'], ['ε', 'epsilon'],
  ['ζ', 'zeta'], ['η', 'eta'], ['θ', 'theta'], ['λ', 'lambda'], ['μ', 'mu'],
  ['ν', 'nu'], ['ξ', 'xi'], ['π', 'pi'], ['ρ', 'rho'], ['σ', 'sigma'],
  ['τ', 'tau'], ['φ', 'phi'], ['χ', 'chi'], ['ψ', 'psi'], ['ω', 'omega'],
].map(([label, name]) => ({ label, insert: `\\${name} `, title: `\\${name}` }))

const greekUpper = [
  ['Γ', 'Gamma'], ['Δ', 'Delta'], ['Θ', 'Theta'], ['Λ', 'Lambda'], ['Ξ', 'Xi'],
  ['Π', 'Pi'], ['Σ', 'Sigma'], ['Φ', 'Phi'], ['Ψ', 'Psi'], ['Ω', 'Omega'],
].map(([label, name]) => ({ label, insert: `\\${name} `, title: `\\${name}` }))

export const SNIPPET_GROUPS: SnippetGroup[] = [
  {
    name: 'Structures',
    items: [
      { label: 'x/y', title: 'fraction', before: '\\frac{', after: '}{}' },
      { label: '√x', title: 'square root', before: '\\sqrt{', after: '}' },
      { label: 'ⁿ√x', title: 'nth root', before: '\\sqrt[n]{', after: '}' },
      { label: 'x²', title: 'superscript', before: '^{', after: '}' },
      { label: 'xₙ', title: 'subscript', before: '_{', after: '}' },
      { label: 'x̄', title: 'overline', before: '\\overline{', after: '}' },
      { label: 'ẋ', title: 'dot (derivative)', before: '\\dot{', after: '}' },
      { label: 'x⃗', title: 'vector', before: '\\vec{', after: '}' },
    ],
  },
  {
    name: 'Big operators',
    items: [
      { label: 'Σ', title: 'sum', before: '\\sum_{', after: '}^{}' },
      { label: 'Π', title: 'product', before: '\\prod_{', after: '}^{}' },
      { label: '∫', title: 'integral', before: '\\int_{', after: '}^{}' },
      { label: '∬', title: 'double integral', insert: '\\iint ' },
      { label: 'lim', title: 'limit', before: '\\lim_{', after: '}' },
      { label: '∂', title: 'partial', insert: '\\partial ' },
      { label: '∇', title: 'nabla', insert: '\\nabla ' },
      { label: '∞', title: 'infinity', insert: '\\infty ' },
    ],
  },
  {
    name: 'Relations & operators',
    items: [
      { label: '≤', insert: '\\leq ' }, { label: '≥', insert: '\\geq ' },
      { label: '≠', insert: '\\neq ' }, { label: '≈', insert: '\\approx ' },
      { label: '±', insert: '\\pm ' }, { label: '×', insert: '\\times ' },
      { label: '÷', insert: '\\div ' }, { label: '·', insert: '\\cdot ' },
      { label: '→', insert: '\\rightarrow ' }, { label: '⇒', insert: '\\Rightarrow ' },
      { label: '∈', insert: '\\in ' }, { label: '∀', insert: '\\forall ' },
      { label: '∃', insert: '\\exists ' }, { label: '∝', insert: '\\propto ' },
    ],
  },
  {
    name: 'Brackets',
    items: [
      { label: '( )', before: '\\left(', after: '\\right)' },
      { label: '[ ]', before: '\\left[', after: '\\right]' },
      { label: '{ }', before: '\\left\\{', after: '\\right\\}' },
      { label: '| |', title: 'absolute value', before: '\\left|', after: '\\right|' },
      { label: '⌈ ⌉', title: 'ceiling', before: '\\lceil', after: '\\rceil' },
      { label: 'matrix', before: '\\begin{pmatrix}', after: ' & \\\\ & \\end{pmatrix}' },
    ],
  },
  {
    name: 'Functions',
    items: [
      { label: 'sin', insert: '\\sin ' }, { label: 'cos', insert: '\\cos ' },
      { label: 'tan', insert: '\\tan ' }, { label: 'ln', insert: '\\ln ' },
      { label: 'log', insert: '\\log ' }, { label: 'exp', insert: '\\exp ' },
      { label: 'min', insert: '\\min ' }, { label: 'max', insert: '\\max ' },
    ],
  },
  { name: 'Greek', items: greekLower },
  { name: 'Greek (upper)', items: greekUpper },
]
