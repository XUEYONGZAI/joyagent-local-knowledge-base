import React, { Suspense } from 'react';
import { createBrowserRouter, Navigate } from 'react-router-dom';
import Layout from '@/layout/index';
import { Loading } from '@/components';

const ROUTES = {
  HOME: '/',
  KNOWLEDGE_RAG: '/knowledge',
  NOT_FOUND: '*',
};

const Home = React.lazy(() => import('@/pages/Home'));
const KnowledgeRAG = React.lazy(() => import('@/pages/KnowledgeRAG'));
const NotFound = React.lazy(() => import('@/components/NotFound'));

const router = createBrowserRouter([
  {
    path: ROUTES.HOME,
    element: <Layout />,
    children: [
      {
        index: true,
        element: (
          <Suspense fallback={<Loading loading={true} className="h-full"/>}>
            <Home />
          </Suspense>
        ),
      },
      {
        path: ROUTES.KNOWLEDGE_RAG,
        element: (
          <Suspense fallback={<Loading loading={true} className="h-full"/>}>
            <KnowledgeRAG />
          </Suspense>
        ),
      },
      {
        path: ROUTES.NOT_FOUND,
        element: (
          <Suspense fallback={<Loading loading={true} className="h-full"/>}>
            <NotFound />
          </Suspense>
        ),
      },
    ],
  },
  {
    path: '*',
    element: <Navigate to={ROUTES.NOT_FOUND} replace />,
  },
]);

export default router;