--
-- PostgreSQL database dump
--

-- \restrict uKZrnmgMLjTrs3UJ2g7dWPPqjJNoyKPmmovsGiBzc9eBw3pJi69uYLMo7JaTOZ4  (commented: pg_dump 18 meta-command, psql 16 doesn't understand)

-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: action_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.action_items (
    id integer NOT NULL,
    project_id integer NOT NULL,
    title character varying(300) NOT NULL,
    details text NOT NULL,
    owner character varying(160),
    due_date date,
    status character varying(20) NOT NULL,
    created_in_meeting_id integer NOT NULL,
    updated_in_meeting_id integer NOT NULL,
    completed_in_meeting_id integer,
    completed_at timestamp with time zone,
    canonical_title character varying(300) DEFAULT ''::character varying NOT NULL,
    title_embedding json
);


--
-- Name: action_items_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.action_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: action_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.action_items_id_seq OWNED BY public.action_items.id;


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: blockers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.blockers (
    id integer NOT NULL,
    project_id integer NOT NULL,
    title character varying(300) NOT NULL,
    description text NOT NULL,
    status character varying(20) NOT NULL,
    created_in_meeting_id integer NOT NULL,
    updated_in_meeting_id integer NOT NULL,
    resolved_in_meeting_id integer,
    resolved_at timestamp with time zone,
    canonical_title character varying(300) DEFAULT ''::character varying NOT NULL,
    title_embedding json
);


--
-- Name: blockers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.blockers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: blockers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.blockers_id_seq OWNED BY public.blockers.id;


--
-- Name: decisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.decisions (
    id integer NOT NULL,
    project_id integer NOT NULL,
    title character varying(300) NOT NULL,
    details text NOT NULL,
    created_in_meeting_id integer NOT NULL,
    canonical_title character varying(300) DEFAULT ''::character varying NOT NULL,
    title_embedding json
);


--
-- Name: decisions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.decisions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: decisions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.decisions_id_seq OWNED BY public.decisions.id;


--
-- Name: history_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.history_events (
    id integer NOT NULL,
    project_id integer NOT NULL,
    meeting_id integer NOT NULL,
    entity_type character varying(40) NOT NULL,
    entity_id integer,
    event_type character varying(40) NOT NULL,
    summary text NOT NULL,
    before_data json,
    after_data json,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: history_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.history_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: history_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.history_events_id_seq OWNED BY public.history_events.id;


--
-- Name: meetings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.meetings (
    id integer NOT NULL,
    project_id integer NOT NULL,
    title character varying(250) NOT NULL,
    source_filename character varying(255),
    original_text text NOT NULL,
    analysis_text text NOT NULL,
    analysis_json json NOT NULL,
    provider character varying(30) NOT NULL,
    model character varying(120) NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: meetings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.meetings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: meetings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.meetings_id_seq OWNED BY public.meetings.id;


--
-- Name: project_states; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_states (
    id integer NOT NULL,
    project_id integer NOT NULL,
    delivery_status character varying(20) NOT NULL,
    progress_summary text NOT NULL,
    completed_items json NOT NULL,
    in_progress_items json NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    updated_in_meeting_id integer
);


--
-- Name: project_states_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.project_states_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: project_states_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.project_states_id_seq OWNED BY public.project_states.id;


--
-- Name: projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.projects (
    id integer NOT NULL,
    name character varying(200) NOT NULL,
    description text NOT NULL,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: projects_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.projects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: projects_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.projects_id_seq OWNED BY public.projects.id;


--
-- Name: review_resolutions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.review_resolutions (
    id integer NOT NULL,
    history_event_id integer NOT NULL,
    action character varying(30) NOT NULL,
    target_item_id integer,
    note text NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: review_resolutions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.review_resolutions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: review_resolutions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.review_resolutions_id_seq OWNED BY public.review_resolutions.id;


--
-- Name: risks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.risks (
    id integer NOT NULL,
    project_id integer NOT NULL,
    title character varying(300) NOT NULL,
    description text NOT NULL,
    impact character varying(20) NOT NULL,
    mitigation text NOT NULL,
    status character varying(20) NOT NULL,
    created_in_meeting_id integer NOT NULL,
    updated_in_meeting_id integer NOT NULL,
    resolved_in_meeting_id integer,
    resolved_at timestamp with time zone,
    canonical_title character varying(300) DEFAULT ''::character varying NOT NULL,
    title_embedding json
);


--
-- Name: risks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.risks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: risks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.risks_id_seq OWNED BY public.risks.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(80) NOT NULL,
    password_hash character varying(255) NOT NULL,
    role character varying(20) DEFAULT 'user'::character varying NOT NULL
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: action_items id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_items ALTER COLUMN id SET DEFAULT nextval('public.action_items_id_seq'::regclass);


--
-- Name: blockers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blockers ALTER COLUMN id SET DEFAULT nextval('public.blockers_id_seq'::regclass);


--
-- Name: decisions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decisions ALTER COLUMN id SET DEFAULT nextval('public.decisions_id_seq'::regclass);


--
-- Name: history_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.history_events ALTER COLUMN id SET DEFAULT nextval('public.history_events_id_seq'::regclass);


--
-- Name: meetings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meetings ALTER COLUMN id SET DEFAULT nextval('public.meetings_id_seq'::regclass);


--
-- Name: project_states id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_states ALTER COLUMN id SET DEFAULT nextval('public.project_states_id_seq'::regclass);


--
-- Name: projects id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects ALTER COLUMN id SET DEFAULT nextval('public.projects_id_seq'::regclass);


--
-- Name: review_resolutions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_resolutions ALTER COLUMN id SET DEFAULT nextval('public.review_resolutions_id_seq'::regclass);


--
-- Name: risks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risks ALTER COLUMN id SET DEFAULT nextval('public.risks_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: action_items action_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_items
    ADD CONSTRAINT action_items_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: blockers blockers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blockers
    ADD CONSTRAINT blockers_pkey PRIMARY KEY (id);


--
-- Name: decisions decisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decisions
    ADD CONSTRAINT decisions_pkey PRIMARY KEY (id);


--
-- Name: history_events history_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.history_events
    ADD CONSTRAINT history_events_pkey PRIMARY KEY (id);


--
-- Name: meetings meetings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meetings
    ADD CONSTRAINT meetings_pkey PRIMARY KEY (id);


--
-- Name: project_states project_states_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_states
    ADD CONSTRAINT project_states_pkey PRIMARY KEY (id);


--
-- Name: project_states project_states_project_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_states
    ADD CONSTRAINT project_states_project_id_key UNIQUE (project_id);


--
-- Name: projects projects_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_name_key UNIQUE (name);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: review_resolutions review_resolutions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_resolutions
    ADD CONSTRAINT review_resolutions_pkey PRIMARY KEY (id);


--
-- Name: risks risks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risks
    ADD CONSTRAINT risks_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: ix_action_items_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_action_items_project_id ON public.action_items USING btree (project_id);


--
-- Name: ix_action_items_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_action_items_status ON public.action_items USING btree (status);


--
-- Name: ix_blockers_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_blockers_project_id ON public.blockers USING btree (project_id);


--
-- Name: ix_blockers_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_blockers_status ON public.blockers USING btree (status);


--
-- Name: ix_decisions_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_decisions_project_id ON public.decisions USING btree (project_id);


--
-- Name: ix_history_events_meeting_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_history_events_meeting_id ON public.history_events USING btree (meeting_id);


--
-- Name: ix_history_events_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_history_events_project_id ON public.history_events USING btree (project_id);


--
-- Name: ix_meetings_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_meetings_project_id ON public.meetings USING btree (project_id);


--
-- Name: ix_review_resolutions_history_event_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_review_resolutions_history_event_id ON public.review_resolutions USING btree (history_event_id);


--
-- Name: ix_risks_project_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_risks_project_id ON public.risks USING btree (project_id);


--
-- Name: ix_risks_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_risks_status ON public.risks USING btree (status);


--
-- Name: uq_action_items_project_canonical_title; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_action_items_project_canonical_title ON public.action_items USING btree (project_id, canonical_title) WHERE ((canonical_title)::text <> ''::text);


--
-- Name: uq_blockers_project_canonical_title; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_blockers_project_canonical_title ON public.blockers USING btree (project_id, canonical_title) WHERE ((canonical_title)::text <> ''::text);


--
-- Name: uq_decisions_project_canonical_title; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_decisions_project_canonical_title ON public.decisions USING btree (project_id, canonical_title) WHERE ((canonical_title)::text <> ''::text);


--
-- Name: uq_risks_project_canonical_title; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_risks_project_canonical_title ON public.risks USING btree (project_id, canonical_title) WHERE ((canonical_title)::text <> ''::text);


--
-- Name: action_items action_items_completed_in_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_items
    ADD CONSTRAINT action_items_completed_in_meeting_id_fkey FOREIGN KEY (completed_in_meeting_id) REFERENCES public.meetings(id);


--
-- Name: action_items action_items_created_in_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_items
    ADD CONSTRAINT action_items_created_in_meeting_id_fkey FOREIGN KEY (created_in_meeting_id) REFERENCES public.meetings(id);


--
-- Name: action_items action_items_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_items
    ADD CONSTRAINT action_items_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: action_items action_items_updated_in_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.action_items
    ADD CONSTRAINT action_items_updated_in_meeting_id_fkey FOREIGN KEY (updated_in_meeting_id) REFERENCES public.meetings(id);


--
-- Name: blockers blockers_created_in_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blockers
    ADD CONSTRAINT blockers_created_in_meeting_id_fkey FOREIGN KEY (created_in_meeting_id) REFERENCES public.meetings(id);


--
-- Name: blockers blockers_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blockers
    ADD CONSTRAINT blockers_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: blockers blockers_resolved_in_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blockers
    ADD CONSTRAINT blockers_resolved_in_meeting_id_fkey FOREIGN KEY (resolved_in_meeting_id) REFERENCES public.meetings(id);


--
-- Name: blockers blockers_updated_in_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.blockers
    ADD CONSTRAINT blockers_updated_in_meeting_id_fkey FOREIGN KEY (updated_in_meeting_id) REFERENCES public.meetings(id);


--
-- Name: decisions decisions_created_in_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decisions
    ADD CONSTRAINT decisions_created_in_meeting_id_fkey FOREIGN KEY (created_in_meeting_id) REFERENCES public.meetings(id);


--
-- Name: decisions decisions_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.decisions
    ADD CONSTRAINT decisions_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: history_events history_events_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.history_events
    ADD CONSTRAINT history_events_meeting_id_fkey FOREIGN KEY (meeting_id) REFERENCES public.meetings(id);


--
-- Name: history_events history_events_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.history_events
    ADD CONSTRAINT history_events_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: meetings meetings_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meetings
    ADD CONSTRAINT meetings_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: project_states project_states_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_states
    ADD CONSTRAINT project_states_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: project_states project_states_updated_in_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_states
    ADD CONSTRAINT project_states_updated_in_meeting_id_fkey FOREIGN KEY (updated_in_meeting_id) REFERENCES public.meetings(id);


--
-- Name: review_resolutions review_resolutions_history_event_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_resolutions
    ADD CONSTRAINT review_resolutions_history_event_id_fkey FOREIGN KEY (history_event_id) REFERENCES public.history_events(id);


--
-- Name: risks risks_created_in_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risks
    ADD CONSTRAINT risks_created_in_meeting_id_fkey FOREIGN KEY (created_in_meeting_id) REFERENCES public.meetings(id);


--
-- Name: risks risks_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risks
    ADD CONSTRAINT risks_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: risks risks_resolved_in_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risks
    ADD CONSTRAINT risks_resolved_in_meeting_id_fkey FOREIGN KEY (resolved_in_meeting_id) REFERENCES public.meetings(id);


--
-- Name: risks risks_updated_in_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risks
    ADD CONSTRAINT risks_updated_in_meeting_id_fkey FOREIGN KEY (updated_in_meeting_id) REFERENCES public.meetings(id);


--
-- PostgreSQL database dump complete
--

\unrestrict uKZrnmgMLjTrs3UJ2g7dWPPqjJNoyKPmmovsGiBzc9eBw3pJi69uYLMo7JaTOZ4

