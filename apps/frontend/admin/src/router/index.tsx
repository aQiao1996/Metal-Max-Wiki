import { createBrowserRouter } from 'react-router-dom'

import { AdminLayout } from '@/layouts/AdminLayout'
import { HomePage } from '@/pages/Home'

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AdminLayout />,
    children: [{ index: true, element: <HomePage /> }],
  },
])
