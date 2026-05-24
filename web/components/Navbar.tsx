'use client'

import Link from 'next/link'
import { ShoppingCart, User, Search } from 'lucide-react'
import { useSession, signOut } from 'next-auth/react'

export function Navbar() {
  const { data: session } = useSession()

  return (
    <nav className="border-b bg-white">
      <div className="container mx-auto flex items-center justify-between px-4 py-4">
        <Link href="/" className="text-2xl font-bold text-primary-600">
          Sharrowkin Market
        </Link>
        
        <div className="flex items-center gap-6">
          <Link href="/products" className="hover:text-primary-600">
            Products
          </Link>
          
          <Link href="/cart" className="hover:text-primary-600">
            <ShoppingCart className="h-6 w-6" />
          </Link>
          
          {session ? (
            <div className="flex items-center gap-4">
              <span className="text-sm">{session.user?.name}</span>
              <button
                onClick={() => signOut()}
                className="text-sm hover:text-primary-600"
              >
                Sign Out
              </button>
            </div>
          ) : (
            <Link href="/auth/signin" className="hover:text-primary-600">
              <User className="h-6 w-6" />
            </Link>
          )}
        </div>
      </div>
    </nav>
  )
}