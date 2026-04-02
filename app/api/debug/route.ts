import { NextResponse } from 'next/server'

export async function GET() {
  return NextResponse.json({
    api_url: process.env.NEXT_PUBLIC_API_URL || 'NO CONFIGURADO — usando localhost:8000',
    node_env: process.env.NODE_ENV,
  })
}
