export type CommandCategory = "user" | "power";

export type DisplayBlock =
  | {
      type: "summary";
      title?: string | null;
      text: string;
    }
  | {
      type: "kv";
      title?: string | null;
      items: Array<{ key: string; value: unknown }>;
    }
  | {
      type: "table";
      title?: string | null;
      columns: string[];
      rows: unknown[][];
    }
  | {
      type: "list";
      title?: string | null;
      items: string[];
    }
  | {
      type: "json";
      title?: string | null;
      value: unknown;
    };

export interface ResultSection {
  section_id: string;
  title: string;
  blocks: DisplayBlock[];
}

export interface SlashCommandSpec {
  name: string;
  usage: string;
  summary: string;
  category: CommandCategory;
  example?: string | null;
}

export interface ExtensionOption {
  alias: string;
  title: string;
  description: string;
}

export interface ScalarFieldSemantics {
  kind: "scalar";
  param: string;
  field_path: string;
  label: string;
  help?: string | null;
  value_type: "number" | "string";
  required: boolean;
  min?: number | null;
  max?: number | null;
  example?: unknown;
}

export interface VectorFieldSemantics {
  kind: "vector";
  param: string;
  over: string;
  field_path: string;
  label: string;
  help?: string | null;
  value_type: "number" | "string";
  required: boolean;
  min?: number | null;
  max?: number | null;
  example?: unknown;
}

export interface TableKeySemantics {
  kind: "table_key";
  set_name: string;
  field_path: string;
  label: string;
  help?: string | null;
  example?: unknown;
}

export interface TableColumnSemantics {
  kind: "table_column";
  param: string;
  set_name: string;
  field_path: string;
  label: string;
  help?: string | null;
  value_type: "number" | "string";
  required: boolean;
  min?: number | null;
  max?: number | null;
  example?: unknown;
}

export interface TableShapeSemantics {
  kind: "table";
  set_name: string;
  key: TableKeySemantics;
  columns: TableColumnSemantics[];
}

export interface MatrixFieldSemantics {
  kind: "matrix_field";
  param: string;
  row_set: string;
  col_set: string;
  field_path: string;
  label: string;
  help?: string | null;
  value_type: "number" | "string";
  required: boolean;
  min?: number | null;
  max?: number | null;
  example?: unknown;
}

export interface MatrixShapeSemantics {
  kind: "matrix";
  row_set: string;
  col_set: string;
  fields: MatrixFieldSemantics[];
}

export interface InputStepSemantics {
  step_id: string;
  label: string;
  scalars: ScalarFieldSemantics[];
  vectors: VectorFieldSemantics[];
  shape?: TableShapeSemantics | MatrixShapeSemantics | null;
  example_command?: string | null;
}

export interface StageInteraction {
  stage_id: string;
  label: string;
  depends_on: string[];
  ready: boolean;
  current: boolean;
  missing: boolean;
  errors: string[];
  expectation_hint?: string | null;
  example_command?: string | null;
}

export interface DisplaySemantics {
  summary: Array<{ id: string; label?: string | null; expr: string }>;
  tables: Array<{
    id: string;
    label?: string | null;
    rows: string;
    columns: Array<{ id: string; label?: string | null; expr: string }>;
  }>;
  matrices: Array<{
    id: string;
    label?: string | null;
    rows: string;
    cols: string;
    cell: string;
  }>;
}

export interface BundleSemantics {
  supported: boolean;
  mode: "declarative_bundle";
  alias: string;
  dsl_format: string;
  wizard_mode: "linear";
  stage_ids: string[];
  display: DisplaySemantics;
  inputs: InputStepSemantics[];
}

export interface InteractionState {
  thread_id: string;
  thread_exists: boolean;
  active_extension: string;
  available_extensions: ExtensionOption[];
  current_stage?: string | null;
  pending_question?: string | null;
  draft_summary?: string | null;
  expected_payload?: Record<string, unknown> | null;
  draft: Record<string, Record<string, unknown>>;
  stage_statuses: StageInteraction[];
  current_step?: InputStepSemantics | null;
  display?: DisplaySemantics | null;
  result_sections: ResultSection[];
  commands: SlashCommandSpec[];
  semantics?: BundleSemantics | null;
}

export interface ThreadSummary {
  thread_id: string;
  extension_alias: string;
  extension_title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_user_message?: string | null;
  pending_question?: string | null;
}

export interface ThreadEnvelope {
  thread: ThreadSummary;
  session: Record<string, unknown>;
  interaction: InteractionState | null;
}
