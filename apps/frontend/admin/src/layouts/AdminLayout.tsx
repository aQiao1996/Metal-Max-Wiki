import { Layout, Typography } from 'antd'
import { Outlet } from 'react-router-dom'

const { Header, Content } = Layout

export function AdminLayout() {
  return (
    <Layout className="admin-shell">
      <Header className="admin-header">
        <Typography.Title level={4} className="admin-title">
          Metal Max Wiki Admin
        </Typography.Title>
      </Header>
      <Content className="admin-content">
        <Outlet />
      </Content>
    </Layout>
  )
}
