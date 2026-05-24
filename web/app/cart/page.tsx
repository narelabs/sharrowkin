import { CartList } from '@/components/CartList'

export default function CartPage() {
  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="mb-8 text-4xl font-bold">Shopping Cart</h1>
      <CartList />
    </div>
  )
}