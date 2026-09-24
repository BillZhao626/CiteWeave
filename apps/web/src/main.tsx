import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import {
  BrowserRouter,
  Link,
  NavLink,
  Outlet,
  Route,
  Routes,
  useNavigate,
} from "react-router";
import {
  QueryClient,
  QueryClientProvider,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { BookOpen, Plus, ArrowUpRight, Layers, LogOut } from "lucide-react";
import { Button } from "./components/ui/button";
import { api, listKBs, message, unwrap, ApiError } from "./api";
import { KnowledgeWorkspace } from "./workspace";
import {
  RunsPage,
  RunInspector,
  EvaluationsPage,
  EvaluationDetail,
  VersionsPage,
  SystemPage,
} from "./operations";
import { DocumentsPage, StructureView } from "./structure-view";
import "./index.css";
import "./product-polish.css";

const client = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, error) =>
        !(error instanceof ApiError && error.status < 500) && count < 1,
      staleTime: 15_000,
      refetchOnWindowFocus: false,
    },
    mutations: { retry: false },
  },
});

function Login() {
  const [token, setToken] = useState(""),
    cache = useQueryClient();
  const login = useMutation({
    mutationFn: async () => {
      const result = await api.POST("/v1/auth/session", { body: { token } });
      if (!result.response.ok) throw new Error("unauthorized");
    },
    onSuccess: () => {
      setToken("");
      void cache.invalidateQueries();
    },
  });
  return (
    <div className="login-wrap">
      <div className="login-copy">
        <div className="brand">
          <Layers /> CiteWeave
        </div>
        <p className="eyebrow">YOUR KNOWLEDGE. ITS EVIDENCE.</p>
        <h1>
          每一个答案，
          <br />
          都有迹可循。
        </h1>
        <p>把文档变成可追溯的知识。检索、回答，再回到原文，核对每一个引用。</p>
        <div className="login-note">个人知识库 · 本地运行 · Alpha</div>
      </div>
      <form
        className="login-card"
        onSubmit={(e) => {
          e.preventDefault();
          login.mutate();
        }}
      >
        <span className="eyebrow">LOCAL WORKSPACE</span>
        <h2>打开你的工作空间</h2>
        <p className="muted">使用本地配置中的工作空间访问令牌登录。</p>
        <label htmlFor="token">访问令牌</label>
        <input
          id="token"
          type="password"
          autoComplete="current-password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          required
        />
        {login.error && (
          <p className="error" role="alert">
            {message(login.error)}
          </p>
        )}
        <Button
          disabled={login.isPending || !token}
          type="submit"
          className="wide"
        >
          {login.isPending ? "正在连接…" : "进入工作空间"}
          <ArrowUpRight />
        </Button>
        <small>
          令牌位于项目 .env 的 CW_ADMIN_TOKEN；登录有效期为 8 小时。
        </small>
      </form>
    </div>
  );
}

function Layout() {
  const kbs = useQuery({ queryKey: ["kbs"], queryFn: listKBs }),
    cache = useQueryClient();
  if (kbs.error instanceof ApiError && kbs.error.status === 401)
    return <Login />;
  if (kbs.isPending)
    return <div className="loading-screen">正在连接工作空间…</div>;
  if (kbs.error)
    return (
      <div className="loading-screen">
        <p role="alert">{message(kbs.error)}</p>
        <Button onClick={() => void kbs.refetch()}>重新连接</Button>
      </div>
    );
  return (
    <div className="shell">
      <aside className="sidebar">
        <Link to="/" className="brand">
          <Layers /> CiteWeave <sup>α</sup>
        </Link>
        <p className="workspace-label">EVIDENCE WORKSPACE</p>
        <NavLink to="/" end className="nav-item">
          <BookOpen size={17} /> 知识库
        </NavLink>
        <nav className="ops-nav" aria-label="产品导航">
          <NavLink className="nav-item" to="/documents">
            文档 / 结构
          </NavLink>
          <NavLink className="nav-item" to="/runs">
            运行 / Trace
          </NavLink>
        </nav>
        <nav className="ops-nav secondary-nav" aria-label="开发与管理">
          <NavLink className="nav-item" to="/evaluations">
            评测
          </NavLink>
          <NavLink className="nav-item" to="/system">
            系统与任务
          </NavLink>
        </nav>
        <div className="side-label">
          我的知识库 <span>{kbs.data.length}</span>
        </div>
        <nav className="kb-nav">
          {kbs.data.map((kb) => (
            <NavLink className="nav-item" key={kb.id} to={`/kb/${kb.id}`}>
              <span className="nav-dot" />
              {kb.name}
            </NavLink>
          ))}
        </nav>
        <div className="side-bottom">
          <p>
            <span className="online-dot" /> 本地工作空间
          </p>
          <small>Portfolio alpha · Local runtime</small>
          <button
            className="text-button"
            onClick={async () => {
              const r = await api.DELETE("/v1/auth/session");
              if (r.response.ok) {
                cache.clear();
                void cache.invalidateQueries();
              }
            }}
          >
            <LogOut size={14} />
            退出登录
          </button>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <span>
            知识与证据 <span className="topbar-divider">/</span> Ask. Trace.
            Verify.
          </span>
          <span className="chip">PORTFOLIO ALPHA</span>
        </header>
        <Outlet />
      </div>
    </div>
  );
}

function Library() {
  const kbs = useQuery({ queryKey: ["kbs"], queryFn: listKBs }),
    cache = useQueryClient(),
    navigate = useNavigate();
  const [name, setName] = useState(""),
    [description, setDescription] = useState(""),
    [creating, setCreating] = useState(false);
  const create = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST("/v1/knowledge-bases", {
          body: { name, description },
          params: { header: { "idempotency-key": crypto.randomUUID() } },
        }),
      ),
    onSuccess: (kb) => {
      void cache.invalidateQueries({ queryKey: ["kbs"] });
      void navigate(`/kb/${kb.id}`);
    },
  });
  return (
    <section className="library">
      <p className="eyebrow">KNOWLEDGE LIBRARY</p>
      <div className="page-title">
        <div>
          <h1>让知识有据可查。</h1>
          <p className="muted">为一个主题建立知识库，从第一份文档开始。</p>
        </div>
        <Button onClick={() => setCreating(!creating)}>
          <Plus />
          新建知识库
        </Button>
      </div>
      {creating && (
        <form
          className="create-form"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <h3>新建知识库</h3>
          <label htmlFor="kb-name">知识库名称</label>
          <input
            id="kb-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={100}
            placeholder="例如：观测站技术手册"
            required
          />
          <label htmlFor="kb-description">简短说明</label>
          <input
            id="kb-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={1000}
            placeholder="这份知识将帮助你解答什么？"
          />
          {create.error && (
            <p className="error" role="alert">
              {message(create.error)}
            </p>
          )}
          <Button type="submit" disabled={create.isPending || !name.trim()}>
            创建并进入
          </Button>
        </form>
      )}
      <div className="library-heading">
        <h3>我的知识库</h3>
        <span>{kbs.data?.length ?? 0} 个知识库</span>
      </div>
      <div className="kb-grid">
        {kbs.data?.map((kb, i) => (
          <Link className="kb-card" key={kb.id} to={`/kb/${kb.id}`}>
            <div className="card-top">
              <span className="book-icon">
                <BookOpen size={22} />
              </span>
              <ArrowUpRight size={18} />
            </div>
            <span className="eyebrow">
              COLLECTION {String(i + 1).padStart(2, "0")}
            </span>
            <h2>{kb.name}</h2>
            <p>{kb.description || "上传文档，建立可溯源的问答空间。"}</p>
            <footer>
              打开知识库 <span>→</span>
            </footer>
          </Link>
        ))}
      </div>
      {!kbs.data?.length && (
        <div className="empty-library">
          <BookOpen size={36} />
          <h2>你的第一份知识，值得认真保存。</h2>
          <p>创建知识库后，上传 PDF 或使用原创示例，体验完整的证据问答。</p>
        </div>
      )}
      <div className="library-note">
        <span>01 上传文档</span>
        <span>02 提出问题</span>
        <span>03 回到原文</span>
        <p>答案绑定版本与精确片段，让引用成为验证的起点。</p>
      </div>
    </section>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Library />} />
            <Route path="kb/:id" element={<KnowledgeWorkspace />} />
            <Route path="documents" element={<DocumentsPage />} />
            <Route path="versions/:id/structure" element={<StructureView />} />
            <Route path="runs" element={<RunsPage />} />
            <Route path="runs/:id" element={<RunInspector />} />
            <Route path="evaluations" element={<EvaluationsPage />} />
            <Route path="evaluations/:id" element={<EvaluationDetail />} />
            <Route path="documents/:id/versions" element={<VersionsPage />} />
            <Route path="system" element={<SystemPage />} />
            <Route path="*" element={<Library />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
