"""Version-bound structure and typed index builds; no historical evidence rewrite."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE cw3_structure_artifacts (
      id uuid PRIMARY KEY, version_id uuid NOT NULL REFERENCES cw1_document_versions(id),
      parser_revision varchar(80) NOT NULL, profile_hash varchar(64) NOT NULL,
      profile jsonb NOT NULL, canonical_sha varchar(64) NOT NULL,
      tree_hash varchar(64) NOT NULL, membership_hash varchar(64) NOT NULL,
      tokenizers jsonb NOT NULL, state varchar(24) NOT NULL CHECK(state IN ('DRAFT','PUBLISHED')),
      UNIQUE(id,version_id));
    CREATE INDEX ON cw3_structure_artifacts(version_id);
    CREATE TABLE cw3_structure_nodes (
      id uuid PRIMARY KEY, artifact_id uuid NOT NULL REFERENCES cw3_structure_artifacts(id),
      parent_node_id uuid, kind varchar(24) NOT NULL, number varchar(80), title text NOT NULL,
      heading_ids jsonb NOT NULL, content_ids jsonb NOT NULL, reading_order integer NOT NULL CHECK(reading_order>=0),
      page_start integer NOT NULL CHECK(page_start>=0), page_end integer NOT NULL CHECK(page_end>=page_start),
      confidence varchar(24) NOT NULL CHECK(confidence IN ('VERIFIED_RULE','HEURISTIC','FALLBACK_PAGE')),
      reasons jsonb NOT NULL, details jsonb NOT NULL, UNIQUE(id,artifact_id),
      CHECK(parent_node_id IS DISTINCT FROM id),
      FOREIGN KEY(parent_node_id,artifact_id) REFERENCES cw3_structure_nodes(id,artifact_id)
        DEFERRABLE INITIALLY DEFERRED);
    CREATE INDEX ON cw3_structure_nodes(artifact_id);
    CREATE TABLE cw3_retrieval_children (
      id uuid PRIMARY KEY, version_id uuid NOT NULL, artifact_id uuid NOT NULL,
      parent_node_id uuid NOT NULL, ordinal integer NOT NULL CHECK(ordinal>=0),
      retrieval_text text NOT NULL, text_hash varchar(64) NOT NULL, membership_hash varchar(64) NOT NULL,
      tokenizers jsonb NOT NULL, token_counts jsonb NOT NULL, details jsonb NOT NULL,
      UNIQUE(id,version_id), UNIQUE(parent_node_id,ordinal),
      FOREIGN KEY(artifact_id,version_id) REFERENCES cw3_structure_artifacts(id,version_id),
      FOREIGN KEY(parent_node_id,artifact_id) REFERENCES cw3_structure_nodes(id,artifact_id));
    CREATE INDEX ON cw3_retrieval_children(version_id);
    CREATE INDEX ON cw3_retrieval_children(artifact_id);
    CREATE INDEX ON cw3_retrieval_children(parent_node_id);
    ALTER TABLE cw1_chunks ADD CONSTRAINT cw3_chunk_version_unique UNIQUE(id,version_id);
    CREATE TABLE cw3_child_spans (
      child_id uuid NOT NULL, evidence_id uuid NOT NULL, version_id uuid NOT NULL,
      position integer NOT NULL CHECK(position>=0), PRIMARY KEY(child_id,evidence_id), UNIQUE(child_id,position),
      FOREIGN KEY(child_id,version_id) REFERENCES cw3_retrieval_children(id,version_id),
      FOREIGN KEY(evidence_id,version_id) REFERENCES cw1_chunks(id,version_id));
    ALTER TABLE cw2_indexes
      ADD COLUMN unit_kind varchar(24) NOT NULL DEFAULT 'legacy_span',
      ADD COLUMN artifact_id uuid,
      ADD COLUMN index_profile_hash varchar(64),
      ADD COLUMN embedding_identity jsonb,
      ADD COLUMN bm25 jsonb,
      ADD COLUMN bm25_hash varchar(64),
      ADD CONSTRAINT cw3_index_artifact_version FOREIGN KEY(artifact_id,version_id)
        REFERENCES cw3_structure_artifacts(id,version_id),
      ADD CONSTRAINT cw3_index_unit CHECK (
        (unit_kind='legacy_span' AND artifact_id IS NULL) OR
        (unit_kind='structural_child' AND artifact_id IS NOT NULL AND index_profile_hash IS NOT NULL
          AND embedding_identity IS NOT NULL AND bm25 IS NOT NULL AND bm25_hash IS NOT NULL));
    """)
    op.execute("""
    CREATE FUNCTION cw3_immutable_structure() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE aid uuid; published boolean;
    BEGIN
      IF TG_TABLE_NAME = 'cw3_structure_artifacts' THEN
        IF TG_OP <> 'INSERT' AND OLD.state = 'PUBLISHED' THEN
          RAISE EXCEPTION 'published_structure_immutable';
        END IF;
      ELSE
        IF TG_TABLE_NAME = 'cw3_child_spans' THEN
          SELECT artifact_id INTO aid FROM cw3_retrieval_children
            WHERE id = CASE WHEN TG_OP='DELETE' THEN OLD.child_id ELSE NEW.child_id END;
        ELSE
          aid := CASE WHEN TG_OP='DELETE' THEN OLD.artifact_id ELSE NEW.artifact_id END;
        END IF;
        SELECT state='PUBLISHED' INTO published FROM cw3_structure_artifacts WHERE id=aid FOR UPDATE;
        IF published THEN RAISE EXCEPTION 'published_structure_immutable'; END IF;
        IF TG_OP='UPDATE' THEN
          IF TG_TABLE_NAME='cw3_child_spans' THEN
            SELECT artifact_id INTO aid FROM cw3_retrieval_children WHERE id=OLD.child_id;
          ELSE aid := OLD.artifact_id; END IF;
          SELECT state='PUBLISHED' INTO published FROM cw3_structure_artifacts WHERE id=aid FOR UPDATE;
          IF published THEN RAISE EXCEPTION 'published_structure_immutable'; END IF;
        END IF;
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
    END $$;
    CREATE TRIGGER cw3_artifact_immutable BEFORE UPDATE OR DELETE ON cw3_structure_artifacts
      FOR EACH ROW EXECUTE FUNCTION cw3_immutable_structure();
    CREATE TRIGGER cw3_node_immutable BEFORE INSERT OR UPDATE OR DELETE ON cw3_structure_nodes
      FOR EACH ROW EXECUTE FUNCTION cw3_immutable_structure();
    CREATE TRIGGER cw3_child_immutable BEFORE INSERT OR UPDATE OR DELETE ON cw3_retrieval_children
      FOR EACH ROW EXECUTE FUNCTION cw3_immutable_structure();
    CREATE TRIGGER cw3_membership_immutable BEFORE INSERT OR UPDATE OR DELETE ON cw3_child_spans
      FOR EACH ROW EXECUTE FUNCTION cw3_immutable_structure();
    """)
    op.execute("""
    CREATE FUNCTION cw3_no_node_cycle() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE cursor_id uuid; visited uuid[] := ARRAY[NEW.id];
    BEGIN
      SELECT parent_node_id INTO cursor_id FROM cw3_structure_nodes WHERE id=NEW.id;
      WHILE cursor_id IS NOT NULL LOOP
        IF cursor_id=ANY(visited) THEN RAISE EXCEPTION 'structure_node_cycle'; END IF;
        visited := array_append(visited,cursor_id);
        SELECT parent_node_id INTO cursor_id FROM cw3_structure_nodes WHERE id=cursor_id;
      END LOOP;
      RETURN NEW;
    END $$;
    CREATE CONSTRAINT TRIGGER cw3_node_acyclic AFTER INSERT OR UPDATE ON cw3_structure_nodes
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION cw3_no_node_cycle();
    CREATE FUNCTION cw3_immutable_source_span() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF EXISTS (SELECT 1 FROM cw3_child_spans m JOIN cw3_retrieval_children c ON c.id=m.child_id
          JOIN cw3_structure_artifacts a ON a.id=c.artifact_id
          WHERE m.evidence_id=OLD.id AND a.state='PUBLISHED') THEN
        RAISE EXCEPTION 'published_structure_span_immutable';
      END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
    END $$;
    CREATE TRIGGER cw3_span_immutable BEFORE UPDATE OR DELETE ON cw1_chunks
      FOR EACH ROW EXECUTE FUNCTION cw3_immutable_source_span();
    CREATE FUNCTION cw3_immutable_index_binding() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.unit_kind='structural_child' AND OLD.state IN ('PUBLISHED','SUPERSEDED') AND
        ROW(NEW.name,NEW.version_id,NEW.workspace_id,NEW.job_id,NEW.fence,NEW.unit_kind,NEW.artifact_id,
          NEW.index_profile_hash,NEW.embedding_identity,NEW.bm25,NEW.bm25_hash)
        IS DISTINCT FROM
        ROW(OLD.name,OLD.version_id,OLD.workspace_id,OLD.job_id,OLD.fence,OLD.unit_kind,OLD.artifact_id,
          OLD.index_profile_hash,OLD.embedding_identity,OLD.bm25,OLD.bm25_hash)
      THEN RAISE EXCEPTION 'published_index_binding_immutable'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER cw3_index_immutable BEFORE UPDATE ON cw2_indexes
      FOR EACH ROW EXECUTE FUNCTION cw3_immutable_index_binding();
    """)


def downgrade():
    raise RuntimeError("structure_expand_only_use_compatible_application")
