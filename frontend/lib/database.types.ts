// Generated from the Supabase schema (project: Samajh / smngfmejqgyjkhpozcwr).
// Regenerate: `supabase gen types typescript --project-id smngfmejqgyjkhpozcwr`
// or via the Supabase MCP `generate_typescript_types`.
export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  public: {
    Tables: {
      digitizations: {
        Row: {
          content: string | null
          content_json: Json | null
          created_at: string
          document_id: string
          id: string
          output_format: string
          page_metrics: Json | null
          sarvam_job_id: string | null
        }
        Insert: {
          content?: string | null
          content_json?: Json | null
          created_at?: string
          document_id: string
          id?: string
          output_format: string
          page_metrics?: Json | null
          sarvam_job_id?: string | null
        }
        Update: {
          content?: string | null
          content_json?: Json | null
          created_at?: string
          document_id?: string
          id?: string
          output_format?: string
          page_metrics?: Json | null
          sarvam_job_id?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "digitizations_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
        ]
      }
      documents: {
        Row: {
          case_id: string | null
          created_at: string
          file_name: string
          file_ref: string | null
          filing_type: string
          id: string
          page_count: number | null
          source_language: string | null
          status: string
          updated_at: string
        }
        Insert: {
          case_id?: string | null
          created_at?: string
          file_name: string
          file_ref?: string | null
          filing_type?: string
          id?: string
          page_count?: number | null
          source_language?: string | null
          status?: string
          updated_at?: string
        }
        Update: {
          case_id?: string | null
          created_at?: string
          file_name?: string
          file_ref?: string | null
          filing_type?: string
          id?: string
          page_count?: number | null
          source_language?: string | null
          status?: string
          updated_at?: string
        }
        Relationships: []
      }
      extractions: {
        Row: {
          created_at: string
          document_id: string
          fields: Json
          filing_type: string | null
          id: string
          model: string | null
        }
        Insert: {
          created_at?: string
          document_id: string
          fields: Json
          filing_type?: string | null
          id?: string
          model?: string | null
        }
        Update: {
          created_at?: string
          document_id?: string
          fields?: Json
          filing_type?: string | null
          id?: string
          model?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "extractions_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
        ]
      }
      translations: {
        Row: {
          created_at: string
          document_id: string
          id: string
          model: string | null
          source_language: string | null
          target_language: string
          translated_text: string
        }
        Insert: {
          created_at?: string
          document_id: string
          id?: string
          model?: string | null
          source_language?: string | null
          target_language: string
          translated_text: string
        }
        Update: {
          created_at?: string
          document_id?: string
          id?: string
          model?: string | null
          source_language?: string | null
          target_language?: string
          translated_text?: string
        }
        Relationships: [
          {
            foreignKeyName: "translations_document_id_fkey"
            columns: ["document_id"]
            isOneToOne: false
            referencedRelation: "documents"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: { [_ in never]: never }
    Functions: { [_ in never]: never }
    Enums: { [_ in never]: never }
    CompositeTypes: { [_ in never]: never }
  }
}
