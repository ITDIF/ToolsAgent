import { render, Text, Box } from 'ink'
import React from 'react'

function App() {
  return (
    <Box>
      <Text color="green">测试界面正常显示！</Text>
    </Box>
  )
}

console.log('开始渲染...')
render(<App />)
console.log('渲染完成！')
