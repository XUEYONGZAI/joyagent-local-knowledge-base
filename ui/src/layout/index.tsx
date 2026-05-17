import { memo, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { ConfigProvider, message, Layout, Menu } from 'antd';
import { HomeOutlined, DatabaseOutlined } from '@ant-design/icons';
import { ConstantProvider } from '@/hooks';
import * as constants from "@/utils/constants";
import { setMessage } from '@/utils';

const { Sider, Content } = Layout;

const ROUTES = {
  HOME: '/',
  KNOWLEDGE_RAG: '/knowledge',
};

const AppLayout: GenieType.FC = memo(() => {
  const [messageApi, messageContent] = message.useMessage();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    setMessage(messageApi);
  }, [messageApi]);

  const menuItems = [
    {
      key: ROUTES.HOME,
      icon: <HomeOutlined />,
      label: '智能助手',
    },
    {
      key: ROUTES.KNOWLEDGE_RAG,
      icon: <DatabaseOutlined />,
      label: '本地知识库',
    },
  ];

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key);
  };

  return (
    <ConfigProvider theme={{ token: { colorPrimary: '#4040FFB2' } }}>
      {messageContent}
      <ConstantProvider value={constants}>
        <Layout style={{ minHeight: '100vh' }}>
          <Sider
            width={200}
            style={{
              background: '#fff',
              borderRight: '1px solid #e8e8e8',
            }}
          >
            <div
              style={{
                height: 64,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderBottom: '1px solid #e8e8e8',
                fontSize: 18,
                fontWeight: 600,
                color: '#1890ff',
              }}
            >
              Genie
            </div>
            <Menu
              mode="inline"
              selectedKeys={[location.pathname]}
              items={menuItems}
              onClick={handleMenuClick}
              style={{
                borderRight: 'none',
                marginTop: 8,
              }}
            />
          </Sider>
          <Layout>
            <Content
              style={{
                background: '#f5f5f5',
                minHeight: '100vh',
              }}
            >
              <Outlet />
            </Content>
          </Layout>
        </Layout>
      </ConstantProvider>
    </ConfigProvider>
  );
});

AppLayout.displayName = 'AppLayout';

export default AppLayout;