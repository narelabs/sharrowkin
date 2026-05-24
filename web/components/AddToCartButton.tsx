'use client'

import { useState } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'

interface Product {
  id: string
  stock: number
}

export function AddToCartButton({ product }: { product: Product }) {
  const { data: session } = useSession()
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [quantity, setQuantity] = useState(1)

  const handleAddToCart = async () => {
    if (!session) {
      router.push('/auth/signin')
      return
    }

    setLoading(true)
    try {
      const response = await fetch('/api/cart', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ productId: product.id, quantity }),
      })

      if (response.ok) {
        router.push('/cart')
      }
    } catch (error) {
      console.error('Failed to add to cart:', error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center gap-4">
      <div className="flex items-center gap-2">
        <button
          onClick={() => setQuantity(Math.max(1, quantity - 1))}
          className="rounded border px-3 py-1"
        >
          -
        </button>
        <span className="w-12 text-center">{quantity}</span>
        <button
          onClick={() => setQuantity(Math.min(product.stock, quantity + 1))}
          className="rounded border px-3 py-1"
        >
          +
        </button>
      </div>
      
      <button
        onClick={handleAddToCart}
        disabled={loading || product.stock === 0}
        className="rounded-lg bg-primary-600 px-8 py-3 font-semibold text-white transition hover:bg-primary-700 disabled:opacity-50"
      >
        {loading ? 'Adding...' : 'Add to Cart'}
      </button>
    </div>
  )
}