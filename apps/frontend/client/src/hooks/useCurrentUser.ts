import { useQuery } from '@tanstack/react-query'

import { currentUserKey, getCurrentUser } from '@/api/auth'

/** 在界面间共享服务器登录状态。 */
export function useCurrentUser() {
  return useQuery({
    queryKey: currentUserKey,
    queryFn: getCurrentUser,
    retry: false,
    staleTime: 30000,
  })
}
